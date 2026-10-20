"""개발 탭: '개발 프로젝트'로 표시한 아이디어에만 보이는 곳.

- 진행 상황: 필요한 기능을 필수(1단계 = 첫 버전) → 있으면 좋음(2단계) → 나중에(3단계) 순서로 얼마나 했나
- 개발 시작: 폴더를 만들고 클로드가 읽을 설명서(CLAUDE.md)·기획서.md·만드는순서.md를 넣어 둠
- 클로드에게 부탁하기: 목적별 부탁 글 + 아이디어 내용을 복사하고 클로드 앱 열기
- 내 규칙: 모든 개발 프로젝트 설명서에 들어가는 규칙 (데이터 폴더의 dev_rules.md)
"""
import os
from datetime import datetime

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

import export
import theme
from store import ACTIVE, FEATURE_PRIORITIES, STATUSES

# 기능 중요도 = 만드는 단계
STAGES = {"필수": "1단계 · 필수 (첫 버전)", "있으면 좋음": "2단계 · 있으면 좋음", "나중에": "3단계 · 나중에"}

DEFAULT_RULES = """- 답은 한국어 반말로, 짧고 쉽게. 개발 용어는 풀어서 설명하기.
- 새로 만들거나 크게 바꾸기 전에 계획을 먼저 보고하고 허락받기.
- 폰 테스트는 테스트 전용 폰(노트10)에서 먼저. 개인 폰(S25)은 내가 말할 때만.
- 업데이트해도 예전 기록(데이터)이 그대로 이어지게. 기록을 지우거나 덮어쓰는 테스트는 진짜 데이터에 하지 않기.
- 기록 파일·비밀번호·토큰·local.properties 같은 건 git에 올리지 않기.
- 화면 글자는 쉬운 한국어로.
"""

# (버튼 글자, 설명, 클로드에게 보낼 부탁 글)
ASKS = [
    ("💬  질문하면서 기획 다듬기",
     "만들기 전에 정해야 할 것을 클로드가 하나씩 물어봐요",
     "아래는 내가 만들려는 앱·프로그램 아이디어야. 실제로 만들기 전에 정해야 할 것들을 나한테 질문해줘. "
     "한 번에 3개 이하로, 쉬운 말로 물어보고, 답을 다 들으면 기획서를 깔끔하게 정리해서 보여줘."),
    ("✂  첫 버전 기능 골라주기",
     "꼭 필요한 것만 남기고 나머지는 나중으로 나눠요",
     "아래 아이디어의 기능들을 보고, 첫 버전에 꼭 있어야 하는 최소한의 기능만 골라줘. "
     "나머지는 '2단계'와 '나중에'로 나누고, 왜 그렇게 나눴는지 한 줄씩 적어줘."),
    ("🔍  빠진 것 찾기",
     "나중에 문제될 만한 점을 미리 짚어줘요",
     "아래 기획에서 빠졌거나 나중에 문제될 만한 점을 찾아줘. 예를 들면 기록 저장·백업, 업데이트 때 예전 기록, "
     "실수로 지웠을 때, 폰·PC 사이 동기화, 처음 쓰는 사람이 헷갈릴 부분 같은 것. 중요한 순서로 짧게."),
    ("🪜  만드는 순서와 확인 방법 짜기",
     "단계별로 나누고, 단계마다 다 됐는지 확인하는 법을 적어줘요",
     "아래 아이디어를 만드는 순서를 단계(1단계, 2단계 …)로 나눠줘. 단계마다 만들 기능과, "
     "그 단계가 다 됐는지 내가 직접 확인할 수 있는 방법(예: '폰에서 적은 게 PC에 뜬다')을 적어줘."),
]


def rules_path(data_dir):
    return os.path.join(data_dir, "dev_rules.md")


def load_rules(data_dir):
    try:
        with open(rules_path(data_dir), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return DEFAULT_RULES


def _section(store, uid, key):
    for s in store.sections(uid):
        if s["key"] == key:
            return s["content"].strip()
    return ""


def roadmap_markdown(store, uid):
    r = store.get(uid)
    out = ["# %s — 만드는 순서" % (r["title"] or "(제목 없음)"), "",
           "> 아이디어 보드에서 만든 파일이야. 위 단계부터 하나씩 만들고, 다 되면 [x]로 체크해줘.",
           "> '확인'은 그 기능이 다 됐는지 직접 확인하는 방법이야.", ""]
    feats = store.features(uid)
    if not feats:
        out += ["_(아직 적은 기능이 없어요. 아이디어 보드의 '필요한 기능' 탭에 적어주세요.)_", ""]
    for pr in FEATURE_PRIORITIES:
        group = [f for f in feats if f["priority"] == pr]
        if not group:
            continue
        out += ["## %s" % STAGES[pr], ""]
        for f in group:
            out.append("- [%s] %s" % ("x" if f["done"] else " ", f["text"]))
            if f["criteria"].strip():
                out.append("  - 확인: %s" % f["criteria"].strip())
        out.append("")
    done = _section(store, uid, "dev_done")
    if done:
        out += ["## 첫 버전 완성 기준", "", done, ""]
    not_now = _section(store, uid, "dev_not_now")
    if not_now:
        out += ["## 첫 버전에서 뺄 것", "", not_now, ""]
    return "\n".join(out).rstrip() + "\n"


def claude_md(store, uid, rules):
    r = store.get(uid)
    out = ["# %s" % (r["title"] or "(제목 없음)"), ""]
    if r["summary"]:
        out += [r["summary"], ""]
    out += ["> 아이디어 보드의 [개발 시작]으로 만든 설명서야. 작업 전에 이 파일과 `기획서.md`, `만드는순서.md`를 읽어줘.",
            "> (`기획서.md`·`만드는순서.md`는 아이디어 보드에서 다시 만들면 새로 써져. 이 파일은 자유롭게 고쳐도 돼.)", ""]
    for key, title in (("intent", "무엇을 왜 만드나"), ("dev_users", "누가 쓰나"), ("tech", "플랫폼 · 기술")):
        text = _section(store, uid, key)
        if text:
            out += ["## %s" % title, "", text, ""]
    out += ["## 일하는 순서", "",
            "1. **살펴보기** — 관련 파일과 코드를 먼저 읽는다.",
            "2. **계획** — 무엇을 어떻게 바꿀지 짧게 보고하고 허락받는다.",
            "3. **만들기** — `만드는순서.md`의 앞 단계 기능부터 하나씩 만든다.",
            "4. **확인** — 기능마다 적힌 '확인' 방법대로 직접 테스트하고 결과를 알려준다.",
            "5. **정리** — 끝난 기능은 `만드는순서.md`에 체크하고, 커밋한다.", "",
            "## 내 규칙", "", rules.strip(), ""]
    return "\n".join(out).rstrip() + "\n"


def write_files(store, uid, folder, rules, claude_too):
    """설명서 파일 쓰기. 돌려주는 값: 쓴 파일 이름 목록"""
    os.makedirs(folder, exist_ok=True)
    files = [("기획서.md", export.idea_markdown(store, uid)), ("만드는순서.md", roadmap_markdown(store, uid))]
    if claude_too:
        files.insert(0, ("CLAUDE.md", claude_md(store, uid, rules)))
    for name, text in files:
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write(text)
    return [n for n, _t in files]


class RulesDialog(QDialog):
    def __init__(self, data_dir, parent=None):
        super().__init__(parent)
        self.data_dir = data_dir
        self.setWindowTitle("내 개발 규칙")
        self.resize(620, 420)
        hint = QLabel("개발을 시작할 때 만드는 설명서(CLAUDE.md)에 들어가는 규칙이에요. "
                      "클로드가 이 프로젝트에서 일할 때 지켜요. 모든 개발 프로젝트에 같이 쓰여요.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:%s;" % theme.TEXT_DIM)
        self.edit = QPlainTextEdit(load_rules(data_dir))
        buttons = QDialogButtonBox()
        buttons.addButton("저장", QDialogButtonBox.AcceptRole)
        reset = buttons.addButton("처음 내용으로", QDialogButtonBox.ResetRole)
        buttons.addButton("취소", QDialogButtonBox.RejectRole)
        reset.clicked.connect(lambda: self.edit.setPlainText(DEFAULT_RULES))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(hint)
        lay.addWidget(self.edit, 1)
        lay.addWidget(buttons)

    def _save(self):
        os.makedirs(self.data_dir, exist_ok=True)
        with open(rules_path(self.data_dir), "w", encoding="utf-8") as f:
            f.write(self.edit.toPlainText().rstrip() + "\n")
        self.accept()


class FolderDialog(QDialog):
    """개발 폴더 고르기 (기본: 지난번 폴더 옆 / D:\\AI Dev / 문서)"""

    def __init__(self, default, parent=None):
        super().__init__(parent)
        self.setWindowTitle("개발 시작")
        self.setMinimumWidth(560)
        info = QLabel("이 폴더에 클로드가 읽을 설명서(CLAUDE.md)와 기획서.md, 만드는순서.md를 만들어요.\n"
                      "클로드 코드에서 이 폴더를 열면 처음부터 아이디어 내용을 알고 시작해요.\n"
                      "폴더 이름은 영어로 해두면 나중에 깃허브에 올릴 때 편해요.")
        info.setStyleSheet("color:%s;" % theme.TEXT_DIM)
        self.path = QLineEdit(default)
        browse = QPushButton("찾아보기…")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        buttons = QDialogButtonBox()
        self.ok = buttons.addButton("만들기", QDialogButtonBox.AcceptRole)
        buttons.addButton("취소", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.path.textChanged.connect(lambda t: self.ok.setEnabled(bool(t.strip())))
        lay = QVBoxLayout(self)
        lay.addWidget(info)
        lay.addSpacing(6)
        lay.addLayout(row)
        lay.addWidget(buttons)

    def _browse(self):
        cur = self.path.text().strip()
        start = cur if os.path.isdir(cur) else os.path.dirname(cur)
        d = QFileDialog.getExistingDirectory(self, "개발 폴더", start)
        if d:
            self.path.setText(os.path.normpath(d))

    def value(self):
        return os.path.normpath(self.path.text().strip())


def _card(title):
    box = QFrame()
    box.setObjectName("devCard")
    box.setStyleSheet("#devCard { background:%s; border:1px solid %s; border-radius:10px; }"
                      % (theme.PANEL, theme.BORDER))
    lay = QVBoxLayout(box)
    lay.setContentsMargins(16, 12, 16, 14)
    lay.setSpacing(8)
    head = QLabel(title)
    f = head.font()
    f.setBold(True)
    f.setPointSize(f.pointSize() + 1)
    head.setFont(f)
    lay.addWidget(head)
    return box, lay


def _dim(text):
    lb = QLabel(text)
    lb.setWordWrap(True)
    lb.setStyleSheet("color:%s;" % theme.TEXT_DIM)
    return lb


class DevView(QWidget):
    changed = Signal(str)

    def __init__(self, store_, data_dir, parent=None):
        super().__init__(parent)
        self.store = store_
        self.data_dir = data_dir
        self.uid = None

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(2, 12, 14, 16)
        lay.setSpacing(12)

        # 진행 상황
        card, cl = _card("진행 상황")
        cl.addWidget(_dim("'필요한 기능' 탭의 중요도가 곧 만드는 순서예요. 필수만 다 되면 첫 버전 완성!"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        self.bars = {}
        for i, pr in enumerate(FEATURE_PRIORITIES):
            name = QLabel(STAGES[pr])
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setFixedHeight(10)
            count = QLabel()
            count.setStyleSheet("color:%s;" % theme.TEXT_DIM)
            grid.addWidget(name, i, 0)
            grid.addWidget(bar, i, 1)
            grid.addWidget(count, i, 2)
            self.bars[pr] = (bar, count)
        grid.setColumnStretch(1, 1)
        cl.addLayout(grid)
        self.criteria_hint = _dim("")
        cl.addWidget(self.criteria_hint)
        lay.addWidget(card)

        # 개발 폴더
        card, cl = _card("개발 폴더")
        self.folder_info = _dim("")
        self.folder_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        cl.addWidget(self.folder_info)
        self.start_btn = QPushButton("📁  개발 시작 — 폴더와 설명서 만들기")
        self.start_btn.clicked.connect(self.start)
        row = QHBoxLayout()
        self.open_btn = QPushButton("폴더 열기")
        self.open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self._folder())))
        self.copy_btn = QPushButton("경로 복사")
        self.copy_btn.clicked.connect(self._copy_path)
        self.regen_btn = QPushButton("설명서 다시 만들기")
        self.regen_btn.setToolTip("기획서.md·만드는순서.md를 지금 내용으로 새로 써요")
        self.regen_btn.clicked.connect(self.regenerate)
        self.move_btn = QPushButton("다른 폴더로…")
        self.move_btn.clicked.connect(self.start)
        for b in (self.open_btn, self.copy_btn, self.regen_btn, self.move_btn):
            row.addWidget(b)
        row.addStretch(1)
        cl.addWidget(self.start_btn, 0, Qt.AlignLeft)
        cl.addLayout(row)
        lay.addWidget(card)

        # 클로드에게 부탁하기
        card, cl = _card("클로드에게 부탁하기")
        cl.addWidget(_dim("누르면 부탁 글과 이 아이디어 내용이 복사되고 클로드 앱이 열려요. 새 대화에 붙여넣기(Ctrl+V)만 하면 돼요."))
        for label, desc, prompt in ASKS:
            b = QPushButton(label)
            b.setStyleSheet("text-align:left; padding:6px 12px;")
            b.clicked.connect(lambda _c=False, p=prompt: self._ask(p))
            r = QHBoxLayout()
            r.addWidget(b)
            r.addWidget(_dim(desc), 1)
            cl.addLayout(r)
        lay.addWidget(card)

        # 내 규칙
        card, cl = _card("내 개발 규칙")
        cl.addWidget(_dim("개발 시작 때 만드는 설명서에 들어가서, 클로드가 그 프로젝트에서 지켜요. 모든 개발 프로젝트 공통이에요."))
        rb = QPushButton("규칙 보기 · 고치기…")
        rb.clicked.connect(lambda: RulesDialog(self.data_dir, self).exec())
        cl.addWidget(rb, 0, Qt.AlignLeft)
        lay.addWidget(card)
        lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ---------- 그리기 ----------
    def load(self, uid):
        self.uid = uid
        self.refresh()

    def refresh(self):
        if not self.uid or self.store.get(self.uid) is None:
            return
        feats = self.store.features(self.uid)
        for pr, (bar, count) in self.bars.items():
            group = [f for f in feats if f["priority"] == pr]
            done = sum(1 for f in group if f["done"])
            bar.setMaximum(max(1, len(group)))
            bar.setValue(done)
            count.setText("%d / %d" % (done, len(group)) if group else "없음")
        with_c = sum(1 for f in feats if f["criteria"].strip())
        if feats:
            self.criteria_hint.setText("완성 기준(확인하는 법)을 적은 기능: %d / %d  — '필요한 기능' 탭에서 기능 아래 칸에 적어요."
                                       % (with_c, len(feats)))
        else:
            self.criteria_hint.setText("아직 기능이 없어요. '필요한 기능' 탭에 먼저 적어보세요.")
        folder = self._folder()
        has = bool(folder)
        if has:
            gone = "" if os.path.isdir(folder) else "  (지금은 없는 폴더예요)"
            self.folder_info.setText("%s%s" % (folder, gone))
        else:
            self.folder_info.setText("아직 개발 폴더가 없어요. 만들 준비가 됐으면 아래 버튼을 눌러요. "
                                     "폴더 안에 클로드가 읽을 설명서와 기획서·만드는 순서 파일이 생겨요.")
        self.start_btn.setVisible(not has)
        for b in (self.open_btn, self.copy_btn, self.regen_btn, self.move_btn):
            b.setVisible(has)

    def _folder(self):
        r = self.store.get(self.uid) if self.uid else None
        return r["dev_folder"] if r is not None else ""

    # ---------- 동작 ----------
    def _default_folder(self):
        r = self.store.get(self.uid)
        name = export.safe_name(r["title"])
        last = self.store.db.execute("SELECT dev_folder FROM ideas WHERE dev_folder<>'' ORDER BY updated_at DESC LIMIT 1").fetchone()
        if last:
            parent = os.path.dirname(last[0])
        elif os.path.isdir(r"D:\AI Dev"):
            parent = r"D:\AI Dev"
        else:
            parent = export._docs_dir()
        return os.path.join(parent, name)

    def start(self):
        if not self.uid:
            return
        dlg = FolderDialog(self._folder() or self._default_folder(), self)
        if dlg.exec() != QDialog.Accepted:
            return
        folder = dlg.value()
        claude_too = True
        if os.path.exists(os.path.join(folder, "CLAUDE.md")):
            claude_too = QMessageBox.question(
                self, "개발 시작", "이 폴더에 CLAUDE.md가 이미 있어요. 새로 만들까요?\n"
                "'아니요'면 원래 CLAUDE.md는 그대로 두고 기획서.md·만드는순서.md만 만들어요.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes
        try:
            names = write_files(self.store, self.uid, folder, load_rules(self.data_dir), claude_too)
        except OSError as e:
            QMessageBox.warning(self, "개발 시작", "파일을 만들지 못했어요.\n%s" % e)
            return
        self.store.update(self.uid, dev_folder=folder)
        r = self.store.get(self.uid)
        if r["status"] == STATUSES[0] and self.store.room_needed([self.uid]) == 0:
            self.store.update(self.uid, status=ACTIVE)      # 보관함 → 진행 중 (자리가 있을 때만)
        self.refresh()
        self.changed.emit(self.uid)
        QMessageBox.information(self, "개발 시작", "만들었어요: %s\n%s\n\n클로드 코드에서 이 폴더를 열고 시작하면 돼요."
                                % (", ".join(names), folder))
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def regenerate(self):
        folder = self._folder()
        if not folder:
            return
        claude_too = False
        if not os.path.exists(os.path.join(folder, "CLAUDE.md")):
            claude_too = True
        else:
            ans = QMessageBox.question(
                self, "설명서 다시 만들기", "기획서.md와 만드는순서.md를 지금 내용으로 새로 써요.\n\n"
                "CLAUDE.md도 새로 만들까요? (클로드가 그 사이 고쳐 둔 내용이 있으면 사라져요)",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.No)
            if ans == QMessageBox.Cancel:
                return
            claude_too = ans == QMessageBox.Yes
        try:
            names = write_files(self.store, self.uid, folder, load_rules(self.data_dir), claude_too)
        except OSError as e:
            QMessageBox.warning(self, "설명서 다시 만들기", "파일을 쓰지 못했어요.\n%s" % e)
            return
        QMessageBox.information(self, "설명서 다시 만들기", "새로 썼어요: %s  (%s)"
                                % (", ".join(names), datetime.now().strftime("%H:%M")))

    def _copy_path(self):
        QGuiApplication.clipboard().setText(self._folder())

    def _ask(self, prompt):
        if self.uid:
            export.send_to_claude(self, self.store, self.uid, prompt + "\n\n")

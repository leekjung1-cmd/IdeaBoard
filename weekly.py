"""2단계: 주간 점검 · 분류 옮기기 · 쇼츠 소재 모아보기 · 주간 시간표."""
from datetime import date, datetime

from PySide6.QtCore import QMimeData, QPoint, QRect, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QDrag, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton, QRadioButton, QScrollArea,
    QVBoxLayout, QWidget,
)

import export
import theme
from store import ACTIVE, CATEGORIES, SLOTS, STATUSES, WEEKDAYS

STALE_DAYS = 7
MIME = "application/x-ideaboard-idea"


def days_since(ms, today=None):
    today = today or date.today()
    return (today - datetime.fromtimestamp(ms / 1000).date()).days


def stale_ideas(store_):
    """멈춘 아이디어: 완료·보류 빼고 일주일 넘게 손 안 댄 것 (오래된 순)."""
    rows = [r for r in store_.ideas() if r["status"] not in ("완료", "보류") and days_since(r["activity"]) >= STALE_DAYS]
    return sorted(rows, key=lambda r: r["activity"])


def _scroll(body):
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.NoFrame)
    sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sc.setWidget(body)
    return sc


def _card():
    box = QFrame()
    box.setObjectName("wCard")
    box.setStyleSheet("#wCard { background:%s; border:1px solid %s; border-radius:10px; }" % (theme.PANEL, theme.BORDER))
    return box


# ---------------------------------------------------------------- 주간 점검

class ReviewDialog(QDialog):
    """멈춘 아이디어를 하나씩 '계속 / 보류 / 버리기'로 정리. '정리 끝내기'를 눌러야 실제로 바뀜."""

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.setWindowTitle("🗓 주간 점검")
        self.resize(720, 640)
        rows = stale_ideas(store_)
        head = QLabel("<b>일주일 넘게 손 안 댄 아이디어 %d개</b><br>"
                      "<span style='color:%s'>하나씩 골라 주세요. <b>계속</b> = 다음 한 걸음을 적고 이어가기 · "
                      "<b>보류</b> = 잠깐 쉬기 · <b>버리기</b> = 목록에서 지우기</span>" % (len(rows), theme.TEXT_DIM))
        head.setWordWrap(True)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(2, 4, 12, 4)
        lay.setSpacing(8)
        self.items = []     # (row, group, step edit)
        for r in rows:
            card = _card()
            cl = QVBoxLayout(card)
            cl.setContentsMargins(12, 8, 12, 10)
            n = days_since(r["activity"])
            col = theme.DANGER if n >= 30 else theme.QUAD[3]
            t = QLabel("<b>%s</b> &nbsp;<span style='color:%s'>%d일째</span> &nbsp;<span style='color:%s'>%s%s</span>"
                       % (r["title"] or "(제목 없음)", col, n, theme.TEXT_DIM, r["status"],
                          (" · 목표 " + r["due_date"]) if r["due_date"] else ""))
            t.setWordWrap(True)
            cl.addWidget(t)
            row = QHBoxLayout()
            g = QButtonGroup(card)
            for i, label in enumerate(("▶ 계속", "⏸ 보류", "🗑 버리기")):
                b = QRadioButton(label)
                g.addButton(b, i)
                row.addWidget(b)
            row.addStretch(1)
            cl.addLayout(row)
            step = QLineEdit(r["next_step"])
            step.setPlaceholderText("👣 계속한다면 다음 한 걸음 (30분 안에 끝낼 것)")
            step.setVisible(False)
            cl.addWidget(step)
            g.idToggled.connect(lambda i, on, step=step: on and (step.setVisible(i == 0), i == 0 and step.setFocus()))
            g.idToggled.connect(lambda *_: self._count())
            lay.addWidget(card)
            self.items.append((r, g, step))
        if not rows:
            e = QLabel("멈춘 아이디어가 없어요. 이번 주 잘했어요! 🎉")
            e.setAlignment(Qt.AlignCenter)
            e.setStyleSheet("color:%s; padding:40px;" % theme.TEXT_DIM)
            lay.addWidget(e)
        lay.addStretch(1)
        self.summary = QLabel()
        self.summary.setStyleSheet("color:%s;" % theme.TEXT_DIM)
        buttons = QDialogButtonBox()
        self.ok = buttons.addButton("정리 끝내기", QDialogButtonBox.AcceptRole)
        buttons.addButton("나중에", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 14)
        outer.addWidget(head)
        outer.addWidget(_scroll(body), 1)
        outer.addWidget(self.summary)
        outer.addWidget(buttons)
        self._count()

    def _count(self):
        picked = [g.checkedId() for _r, g, _s in self.items]
        n = sum(1 for i in picked if i >= 0)
        self.summary.setText("%d / %d개 골랐어요 (안 고른 건 그대로 둬요)" % (n, len(self.items)))

    def _apply(self):
        keep = [(r, s.text().strip()) for r, g, s in self.items if g.checkedId() == 0]
        pause = [r for r, g, _s in self.items if g.checkedId() == 1]
        drop = [r for r, g, _s in self.items if g.checkedId() == 2]
        if drop and QMessageBox.question(
                self, "버리기", "%d개를 버릴까요? (목록에서 지워져요)\n\n%s" % (
                    len(drop), "\n".join("· " + (r["title"] or "(제목 없음)") for r in drop[:10]))) != QMessageBox.Yes:
            return
        for r, step in keep:
            if step and step != r["next_step"]:
                self.store.update(r["uuid"], next_step=step)
            else:
                self.store.touch(r["uuid"])
        if pause:
            self.store.set_status_many([r["uuid"] for r in pause], "보류")
        if drop:
            self.store.delete_many([r["uuid"] for r in drop])
        self.result_text = "계속 %d · 보류 %d · 버림 %d" % (len(keep), len(pause), len(drop))
        self.accept()


# ---------------------------------------------------------------- 분류 옮기기

class CategoryMoveDialog(QDialog):
    """예전 분류(일상·취미·업무…)를 목표 분류(클로드 실력·수익화·네트워크·운동·기타)로 옮기기."""

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.setWindowTitle("분류 옮기기")
        self.resize(600, 560)
        rows = store_.old_category_ideas()
        head = QLabel("분류가 <b>목표 기준</b>으로 바뀌었어요: %s<br>"
                      "<span style='color:%s'>아이디어마다 새 분류를 골라 주세요. '그대로'로 두면 안 바뀌어요.</span>"
                      % (" · ".join(CATEGORIES), theme.TEXT_DIM))
        head.setWordWrap(True)
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(2, 4, 12, 4)
        grid.setVerticalSpacing(8)
        self.combos = []
        for i, r in enumerate(rows):
            t = QLabel("<b>%s</b>" % (r["title"] or "(제목 없음)"))
            old = QLabel("지금: %s" % (r["category"] or "없음"))
            old.setStyleSheet("color:%s;" % theme.TEXT_DIM)
            c = QComboBox()
            c.addItem("그대로", None)
            for cat in CATEGORIES:
                c.addItem(cat, cat)
            grid.addWidget(t, i, 0)
            grid.addWidget(old, i, 1)
            grid.addWidget(c, i, 2)
            self.combos.append((r, c))
        grid.setColumnStretch(0, 1)
        grid.setRowStretch(len(rows), 1)
        buttons = QDialogButtonBox()
        buttons.addButton("옮기기", QDialogButtonBox.AcceptRole)
        buttons.addButton("나중에", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.addWidget(head)
        lay.addWidget(_scroll(body), 1)
        lay.addWidget(buttons)

    def _apply(self):
        n = 0
        for r, c in self.combos:
            cat = c.currentData()
            if cat and cat != r["category"]:
                self.store.update(r["uuid"], category=cat)
                n += 1
        self.moved = n
        self.accept()


# ---------------------------------------------------------------- 쇼츠 소재 모아보기

SHORTS_PROMPT = ("아래는 내가 '쇼츠 소재'로 표시해 둔 아이디어들이야. 각각 60초 안쪽 세로 영상(쇼츠)으로 만든다면 "
                 "첫 3초 훅, 보여줄 장면 순서, 자막 한 줄씩을 짧게 제안해줘.\n\n")


def shorts_markdown(store_):
    out = ["# 쇼츠 소재 모음", ""]
    for r in store_.ideas():
        if not r["shorts"]:
            continue
        out.append("## %s" % (r["title"] or "(제목 없음)"))
        if r["summary"]:
            out.append("> %s" % r["summary"])
        if r["category"]:
            out.append("- 분류: %s" % r["category"])
        memos = store_.memos(r["uuid"])
        for m in memos[-5:]:
            out.append("- 메모: %s" % m["body"].strip().replace("\n", " "))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


class ShortsDialog(QDialog):
    opened = Signal(str)

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.setWindowTitle("🎬 쇼츠 소재 모아보기")
        self.resize(640, 560)
        rows = [r for r in store_.ideas() if r["shorts"]]
        head = QLabel("<b>쇼츠 소재 %d개</b> &nbsp;<span style='color:%s'>아이디어 화면 위 '🎬 쇼츠'를 켜면 여기 모여요. "
                      "누르면 그 아이디어가 열려요.</span>" % (len(rows), theme.TEXT_DIM))
        head.setWordWrap(True)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        for r in rows:
            memos = store_.memos(r["uuid"])
            text = (r["title"] or "(제목 없음)") + ("\n  " + r["summary"] if r["summary"] else "") + \
                   ("\n  메모 %d개 · %s" % (len(memos), r["category"] or "분류 없음"))
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, r["uuid"])
            self.list.addItem(it)
        if not rows:
            self.list.addItem("아직 없어요. 영상으로 만들 만한 아이디어(여행, 장비 등)에서 '🎬 쇼츠'를 켜 보세요.")
        self.list.itemDoubleClicked.connect(self._open)
        self.list.itemClicked.connect(self._open)
        copy = QPushButton("모두 복사 (마크다운)")
        copy.clicked.connect(lambda: (QGuiApplication.clipboard().setText(shorts_markdown(store_)),
                                      QMessageBox.information(self, "복사", "쇼츠 소재를 모두 복사했어요.")))
        claude = QPushButton("클로드에게 쇼츠 구성 부탁하기")
        claude.clicked.connect(self._claude)
        copy.setEnabled(bool(rows))
        claude.setEnabled(bool(rows))
        row = QHBoxLayout()
        row.addWidget(copy)
        row.addWidget(claude)
        row.addStretch(1)
        close = QPushButton("닫기")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.addWidget(head)
        lay.addWidget(self.list, 1)
        lay.addLayout(row)

    def _open(self, it):
        uid = it.data(Qt.UserRole)
        if uid:
            self.opened.emit(uid)
            self.accept()

    def _claude(self):
        QGuiApplication.clipboard().setText(SHORTS_PROMPT + shorts_markdown(self.store))
        opened = QDesktopServices.openUrl(QUrl("claude://"))
        QMessageBox.information(self, "클로드", "쇼츠 소재와 부탁 글을 복사했어요.\n" +
                                ("클로드 새 대화에 붙여넣기(Ctrl+V) 하세요." if opened else
                                 "클로드를 열고 새 대화에 붙여넣기(Ctrl+V) 하세요."))


# ---------------------------------------------------------------- 주간 시간표

class IdeaPool(QListWidget):
    """끌어다 놓을 아이디어 목록 (진행 중 먼저)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)

    def startDrag(self, actions):
        it = self.currentItem()
        if it is None or not it.data(Qt.UserRole):
            return
        md = QMimeData()
        md.setData(MIME, it.data(Qt.UserRole).encode())
        md.setText(it.text())
        drag = QDrag(self)
        drag.setMimeData(md)
        fm = self.fontMetrics()
        w = min(260, fm.horizontalAdvance(it.text()) + 24)
        pm = QPixmap(w, 28)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(theme.ACCENT), 1.5))
        p.setBrush(QColor(theme.ITEM_SEL))
        p.drawRoundedRect(QRect(1, 1, w - 2, 26), 8, 8)
        p.setPen(QColor(theme.TEXT))
        p.drawText(QRect(10, 0, w - 16, 28), Qt.AlignVCenter, fm.elidedText(it.text(), Qt.ElideRight, w - 16))
        p.end()
        drag.setPixmap(pm)
        drag.setHotSpot(QPoint(12, 14))
        drag.exec(Qt.CopyAction)


class SlotCell(QFrame):
    dropped = Signal(int, int, str, str)    # 요일, 칸, 아이디어 (''= 비움), 옮겨 온 칸 "요일,칸" (없으면 '')
    opened = Signal(str)

    def __init__(self, weekday, slot, today, parent=None):
        super().__init__(parent)
        self.weekday, self.slot = weekday, slot
        self.today = today
        self.uid = None
        self.from_cell = None
        self.setAcceptDrops(True)
        self.setMinimumSize(120, 58)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 5, 6, 5)
        lay.addWidget(self.label)
        self.set_row(None)

    def set_row(self, r, over=False):
        self.uid = r["idea_uuid"] if r is not None else None
        if r is not None:
            text = "<b>%s</b>" % (r["title"] or "(제목 없음)")
            if r["next_step"]:
                text += "<br><span style='color:%s'>👣 %s</span>" % (theme.TEXT_DIM, r["next_step"])
            self.label.setText(text)
            self.setToolTip("누르면 열기 · 오른쪽 클릭으로 비우기 · 다른 칸으로 끌어 옮기기")
        else:
            self.label.setText("<span style='color:%s'>여기에 끌어다 놓기</span>" % theme.TEXT_OFF if over else "")
            self.setToolTip("왼쪽 아이디어를 끌어다 놓으세요")
        bg = theme.ITEM_SEL if r is not None else theme.PANEL
        border = theme.ACCENT if over else (theme.QUAD[2] if self.today else theme.BORDER)
        self.setStyleSheet("SlotCell { background:%s; border:1px %s %s; border-radius:8px; }"
                           % (bg, "solid" if r is not None or over else "dashed", border))

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasFormat(MIME):
            ev.acceptProposedAction()
            self.setStyleSheet(self.styleSheet().replace(theme.BORDER, theme.ACCENT))

    def dragLeaveEvent(self, ev):
        self.setStyleSheet(self.styleSheet().replace(theme.ACCENT, theme.BORDER))

    def dropEvent(self, ev):
        uid = bytes(ev.mimeData().data(MIME)).decode()
        src = bytes(ev.mimeData().data(MIME + "-from")).decode()
        ev.acceptProposedAction()
        self.dropped.emit(self.weekday, self.slot, uid, src)

    def mousePressEvent(self, ev):
        self._press = ev.position().toPoint()

    def mouseMoveEvent(self, ev):
        if self.uid and (ev.position().toPoint() - self._press).manhattanLength() > 8:
            md = QMimeData()
            md.setData(MIME, self.uid.encode())
            md.setData(MIME + "-from", ("%d,%d" % (self.weekday, self.slot)).encode())
            drag = QDrag(self)
            drag.setMimeData(md)
            drag.setPixmap(self.grab())
            drag.exec(Qt.MoveAction | Qt.CopyAction)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.uid and (ev.position().toPoint() - self._press).manhattanLength() <= 8:
            self.opened.emit(self.uid)

    def contextMenuEvent(self, ev):
        if not self.uid:
            return
        m = QMenu(self)
        m.addAction("열기", lambda: self.opened.emit(self.uid))
        m.addAction("비우기", lambda: self.dropped.emit(self.weekday, self.slot, "", ""))
        m.exec(ev.globalPos())


class TimetableWindow(QWidget):
    """주간 시간표: 평일 밤 9시 반부터 30분 칸에 아이디어를 끌어다 놓기 (매주 같은 시간표)."""
    changed = Signal()
    openIdea = Signal(str)

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.setWindowTitle("▥ 주간 시간표")
        self.resize(1000, 520)
        hint = QLabel("평일 밤 9시 반부터 30분씩. 왼쪽 아이디어를 칸에 끌어다 놓으면 그 시간에 할 일이 돼요. "
                      "칸은 다음 한 걸음(30분)과 짝이에요. 매주 같은 시간표로 쓰여요.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:%s;" % theme.TEXT_DIM)
        self.pool = IdeaPool()
        self.pool.setFixedWidth(230)
        self.pool.setAcceptDrops(True)
        self.grid = QGridLayout()
        self.grid.setSpacing(6)
        today = date.today().weekday()
        for d, name in enumerate(WEEKDAYS):
            h = QLabel(name + ("  (오늘)" if d == today else ""))
            h.setAlignment(Qt.AlignCenter)
            h.setStyleSheet("font-weight:bold; color:%s;" % (theme.QUAD[2] if d == today else theme.TEXT))
            self.grid.addWidget(h, 0, d + 1)
        self.cells = {}
        for s, t in enumerate(SLOTS):
            lb = QLabel(t)
            lb.setStyleSheet("color:%s;" % theme.TEXT_DIM)
            self.grid.addWidget(lb, s + 1, 0, Qt.AlignTop | Qt.AlignRight)
            for d in range(len(WEEKDAYS)):
                c = SlotCell(d, s, d == today)
                c.dropped.connect(self._dropped)
                c.opened.connect(self.openIdea)
                self.grid.addWidget(c, s + 1, d + 1)
                self.cells[(d, s)] = c
        for d in range(len(WEEKDAYS)):
            self.grid.setColumnStretch(d + 1, 1)
        left = QVBoxLayout()
        lt = QLabel("아이디어 (진행 중 먼저)")
        lt.setStyleSheet("font-weight:bold;")
        left.addWidget(lt)
        left.addWidget(self.pool, 1)
        body = QHBoxLayout()
        body.addLayout(left)
        body.addLayout(self.grid, 1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.addWidget(hint)
        lay.addLayout(body, 1)

    def showEvent(self, ev):
        self.refresh()
        super().showEvent(ev)

    def refresh(self):
        rows = [r for r in self.store.ideas() if r["status"] not in ("완료", "보류")]
        rows.sort(key=lambda r: (r["status"] != ACTIVE, -r["activity"]))
        self.pool.clear()
        for r in rows:
            it = QListWidgetItem(("▶ " if r["status"] == ACTIVE else "") + (r["title"] or "(제목 없음)"))
            it.setData(Qt.UserRole, r["uuid"])
            it.setToolTip("👣 " + r["next_step"] if r["next_step"] else "끌어서 시간표 칸에 놓기")
            if r["status"] == ACTIVE:
                it.setForeground(QColor(theme.ACCENT))
            self.pool.addItem(it)
        tt = self.store.timetable()
        for key, cell in self.cells.items():
            cell.set_row(tt.get(key))

    def _dropped(self, weekday, slot, uid, src):
        if src and src != "%d,%d" % (weekday, slot):      # 다른 칸에서 옮겨 왔으면 그 칸은 비움
            d, s = map(int, src.split(","))
            self.store.set_slot(d, s, None)
        self.store.set_slot(weekday, slot, uid or None)
        self.refresh()
        self.changed.emit()


def tonight(store_, today=None):
    """오늘 밤 시간표 [(시각, 행)] (주말이면 빈 목록)."""
    d = (today or date.today()).weekday()
    if d >= len(WEEKDAYS):
        return []
    tt = store_.timetable()
    return [(SLOTS[s], tt[(d, s)]) for s in range(len(SLOTS)) if (d, s) in tt]

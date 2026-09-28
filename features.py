"""필요한 기능 탭: 아이디어에 필요한 기능을 중요도(필수 / 있으면 좋음 / 나중에)별로 적고 끝나면 체크."""
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
    QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

import theme
from store import FEATURE_PRIORITIES

PRIORITY_COLORS = {"필수": theme.QUAD[1], "있으면 좋음": theme.QUAD[2], "나중에": theme.QUAD[4]}


class FeatureRow(QWidget):
    request = Signal(str, str, object)      # 기능 uuid, 동작, 값

    def __init__(self, row, first, last, parent=None):
        super().__init__(parent)
        self.fid = row["uuid"]
        self.saved_text = row["text"]
        done = bool(row["done"])
        self.check = QCheckBox()
        self.check.setChecked(done)
        self.check.setToolTip("끝냈으면 체크")
        self.check.toggled.connect(lambda on: self.request.emit(self.fid, "done", on))
        self.text = QLineEdit(row["text"])
        f = self.text.font()
        f.setStrikeOut(done)
        self.text.setFont(f)
        self.text.setStyleSheet(
            "QLineEdit { border:1px solid transparent; background:transparent; padding:2px 4px; color:%s; }"
            "QLineEdit:hover { border-color:%s; } QLineEdit:focus { border-color:%s; background:%s; color:%s; }"
            % (theme.TEXT_DIM if done else theme.TEXT, theme.BORDER, theme.ACCENT, theme.BASE, theme.TEXT))
        self.text.editingFinished.connect(self._save_text)
        more = QToolButton()
        more.setText("⋯")
        more.setPopupMode(QToolButton.InstantPopup)
        more.setStyleSheet("QToolButton { padding:0 8px; color:%s; font-size:13pt; } "
                           "QToolButton::menu-indicator { image:none; }" % theme.TEXT_DIM)
        m = QMenu(more)
        up = m.addAction("위로", lambda: self.request.emit(self.fid, "move", -1))
        down = m.addAction("아래로", lambda: self.request.emit(self.fid, "move", 1))
        up.setEnabled(not first)
        down.setEnabled(not last)
        sub = m.addMenu("중요도 바꾸기")
        for pr in FEATURE_PRIORITIES:
            a = sub.addAction(pr, lambda pr=pr: self.request.emit(self.fid, "priority", pr))
            a.setEnabled(pr != row["priority"])
        m.addSeparator()
        m.addAction("삭제", lambda: self.request.emit(self.fid, "delete", None))
        more.setMenu(m)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.check)
        lay.addWidget(self.text, 1)
        lay.addWidget(more)

    def _save_text(self):
        t = self.text.text().strip()
        if t and t != self.saved_text:
            self.saved_text = t
            self.request.emit(self.fid, "text", t)
        elif not t:
            self.text.setText(self.saved_text)


class FeatureView(QWidget):
    changed = Signal(str)
    countChanged = Signal(int, int)     # 끝낸 수, 전체 수

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.uid = None

        self.input = QLineEdit()
        self.input.setPlaceholderText("필요한 기능을 적고 Enter  (예: 폰과 동기화, 다크 모드)")
        self.input.returnPressed.connect(self.add)
        self.priority = QComboBox()
        self.priority.addItems(FEATURE_PRIORITIES)
        add = QPushButton("추가")
        add.clicked.connect(self.add)
        self.hide_done = QCheckBox("끝낸 것 숨기기")
        self.hide_done.toggled.connect(lambda _on: self.load(self.uid, keep_scroll=True) if self.uid else None)

        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(self.input, 1)
        top.addWidget(self.priority)
        top.addWidget(add)
        opts = QHBoxLayout()
        opts.addStretch(1)
        opts.addWidget(self.hide_done)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(6)
        lay.addLayout(top)
        lay.addLayout(opts)
        lay.addWidget(self.scroll, 1)

    def load(self, uid, keep_scroll=False):
        self.uid = uid
        sb = self.scroll.verticalScrollBar()
        pos = sb.value() if keep_scroll else 0
        rows = self.store.features(uid)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(2, 4, 14, 16)
        lay.setSpacing(2)
        if not rows:
            empty = QLabel("아직 적은 기능이 없어요.\n위 칸에 필요한 기능을 하나씩 적어보세요. 메모 탭의 메모도 ⋯ 메뉴로 여기에 넣을 수 있어요.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color:%s; padding:30px;" % theme.TEXT_DIM)
            lay.addWidget(empty)
        for pr in FEATURE_PRIORITIES:
            group = [r for r in rows if r["priority"] == pr]
            if not group:
                continue
            done = sum(1 for r in group if r["done"])
            head = QLabel("<span style='color:%s; font-weight:bold'>● %s</span>"
                          "&nbsp;&nbsp;<span style='color:%s'>%d / %d</span>"
                          % (PRIORITY_COLORS[pr], pr, theme.TEXT_DIM, done, len(group)))
            head.setStyleSheet("padding:10px 2px 2px 2px;")
            lay.addWidget(head)
            shown = [r for r in group if not (self.hide_done.isChecked() and r["done"])]
            for i, r in enumerate(shown):
                w = FeatureRow(r, i == 0, i == len(shown) - 1)
                w.request.connect(self._on_request)
                lay.addWidget(w)
            if len(shown) < len(group):
                more = QLabel("끝낸 것 %d개 숨김" % (len(group) - len(shown)))
                more.setStyleSheet("color:%s; padding:2px 30px;" % theme.TEXT_OFF)
                lay.addWidget(more)
        lay.addStretch(1)
        self.scroll.setWidget(body)
        QTimer.singleShot(0, lambda: sb.setValue(pos))
        self.countChanged.emit(sum(1 for r in rows if r["done"]), len(rows))

    def add(self):
        text = self.input.text().strip()
        if not text or not self.uid:
            return
        self.store.add_feature(self.uid, text, self.priority.currentText())
        self.input.clear()
        self.load(self.uid, keep_scroll=True)
        sb = self.scroll.verticalScrollBar()
        self.changed.emit(self.uid)

    def add_text(self, text):
        """메모 등에서 넘어온 글을 기능으로 추가."""
        if self.uid:
            self.store.add_feature(self.uid, " ".join(text.split()), FEATURE_PRIORITIES[0])
            self.load(self.uid, keep_scroll=True)
            self.changed.emit(self.uid)

    def _on_request(self, fid, what, value):
        if what == "done":
            self.store.update_feature(fid, done=1 if value else 0)
        elif what == "text":
            self.store.update_feature(fid, text=value)
            self.changed.emit(self.uid)
            return      # 글만 바뀐 건 다시 그릴 필요 없음 (커서 유지)
        elif what == "priority":
            self.store.update_feature(fid, priority=value)
        elif what == "move":
            self.store.move_feature(fid, value)
        elif what == "delete":
            if QMessageBox.question(self, "기능 삭제", "이 기능을 목록에서 지울까요?") != QMessageBox.Yes:
                return
            self.store.delete_feature(fid)
        # 체크 신호 안에서 위젯을 지우지 않게 다음 차례에 다시 그림
        QTimer.singleShot(0, lambda: self.load(self.uid, keep_scroll=True))
        self.changed.emit(self.uid)

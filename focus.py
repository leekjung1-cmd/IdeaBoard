"""손대게 만들기: 진행 중은 3개까지 + 아이디어마다 '다음 한 걸음'.

- ensure_room(): 진행 중으로 올리려는데 자리가 없으면, 지금 진행 중인 것을 완료·보류로 정리하는 창을 띄움
- NextStepBar: 아이디어 화면의 '다음 한 걸음' 칸 + '했어요' 버튼
"""
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

import icons
import theme
from store import ACTIVE, ACTIVE_LIMIT

STEP_HINT = "30분 안에 끝낼 수 있는 다음 행동 1개 (예: 화면 그림 한 장 그리기, 비슷한 앱 3개 찾아보기)"


class RoomDialog(QDialog):
    """진행 중이 꽉 찼을 때: 하나를 완료·보류로 내려야 새 걸 올릴 수 있음."""

    def __init__(self, store_, uids, new, parent=None):
        super().__init__(parent)
        self.store = store_
        self.uids, self.new = list(uids), new
        self.setWindowTitle("진행 중은 %d개까지" % ACTIVE_LIMIT)
        self.setMinimumWidth(500)
        head = QLabel("진행 중은 <b>%d개까지만</b> 둘 수 있어요.<br>"
                      "새로 올리려면 지금 진행 중인 것 중 하나를 <b>완료</b>하거나 <b>보류</b>로 내려 주세요."
                      % ACTIVE_LIMIT)
        head.setWordWrap(True)
        self.need = QLabel()
        self.need.setStyleSheet("color:%s;" % theme.QUAD[3])
        self.rows = QVBoxLayout()
        self.rows.setSpacing(4)
        buttons = QDialogButtonBox()
        self.ok = buttons.addButton("이제 올리기", QDialogButtonBox.AcceptRole)
        buttons.addButton("그만두기 (보관함에 둠)", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 14)
        lay.setSpacing(10)
        lay.addWidget(head)
        lay.addLayout(self.rows)
        lay.addWidget(self.need)
        lay.addWidget(buttons)
        self._fill()

    def _fill(self):
        while self.rows.count():
            w = self.rows.takeAt(0).widget()
            if w:
                w.deleteLater()
        for r in self.store.active_ideas():
            if r["uuid"] in self.uids:
                continue
            box = QFrame()
            box.setObjectName("roomRow")
            box.setStyleSheet("#roomRow { background:%s; border:1px solid %s; border-radius:8px; }"
                              % (theme.PANEL, theme.BORDER))
            hl = QHBoxLayout(box)
            hl.setContentsMargins(10, 6, 6, 6)
            text = "<b>%s</b>" % (r["title"] or "(제목 없음)")
            if r["next_step"]:
                text += "<br><span style='color:%s'>→ %s</span>" % (theme.TEXT_DIM, r["next_step"])
            lb = QLabel(text)
            lb.setWordWrap(True)
            hl.addWidget(lb, 1)
            for st, label in (("완료", "완료"), ("보류", "보류")):
                b = QPushButton(label)
                b.clicked.connect(lambda _c=False, uid=r["uuid"], st=st: self._set(uid, st))
                hl.addWidget(b)
            self.rows.addWidget(box)
        n = self.store.room_needed(self.uids, self.new)
        self.need.setText("%d개 더 내려야 해요" % n if n else "자리가 생겼어요. '이제 올리기'를 누르세요.")
        self.need.setStyleSheet("color:%s;" % (theme.QUAD[3] if n else theme.QUAD[2]))
        self.ok.setEnabled(n == 0)

    def _set(self, uid, status):
        self.store.update(uid, status=status)
        self.changed = True
        QTimer.singleShot(0, self._fill)


def ensure_room(parent, store_, uids=(), new=0):
    """uids(+새 아이디어 new 개)를 진행 중으로 올려도 되는지. 꽉 찼으면 정리 창. 돌려주는 값: 올려도 되면 True"""
    if store_.room_needed(uids, new) == 0:
        return True
    return RoomDialog(store_, uids, new, parent).exec() == QDialog.Accepted


class NextStepBar(QFrame):
    """다음 한 걸음: 글을 적으면 저장, '했어요' 누르면 메모에 기록하고 비운 뒤 새 걸음을 적게 안내."""
    changed = Signal(str)       # uid
    finished = Signal(str)      # uid (메모가 하나 늘었음)

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.uid = None
        self.setObjectName("stepBar")
        icon = QLabel("다음 한 걸음")
        f = icon.font()
        f.setBold(True)
        icon.setFont(f)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(STEP_HINT)
        self.edit.textEdited.connect(lambda _t: self._timer.start())
        self.edit.editingFinished.connect(self.flush)
        self.edit.returnPressed.connect(self.flush)
        self.done_btn = QPushButton(" 했어요")
        self.done_btn.setIcon(icons.icon("check"))
        self.done_btn.setToolTip("끝냈으면 누르세요. 메모에 기록하고 다음 한 걸음을 새로 적게 해요.")
        self.done_btn.clicked.connect(self._done)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.hide()
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(icon)
        row.addWidget(self.edit, 1)
        row.addWidget(self.done_btn)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 10, 8)
        lay.setSpacing(4)
        lay.addLayout(row)
        lay.addWidget(self.note)
        self._timer = QTimer(self, singleShot=True, interval=500)
        self._timer.timeout.connect(self.flush)
        self._note_timer = QTimer(self, singleShot=True, interval=8000)
        self._note_timer.timeout.connect(self._style)

    def load(self, uid):
        self.flush()
        self.uid = uid
        row = self.store.get(uid)
        self.edit.setText(row["next_step"] if row is not None else "")
        self.edit.setCursorPosition(0)
        self.edit.setPlaceholderText(STEP_HINT)
        self._note_timer.stop()
        self._style()

    def flush(self):
        self._timer.stop()
        if not self.uid:
            return
        row = self.store.get(self.uid)
        t = self.edit.text().strip()
        if row is not None and t != row["next_step"]:
            self.store.update(self.uid, next_step=t)
            self.changed.emit(self.uid)
        self._style()

    def _done(self):
        self.flush()
        step = self.store.finish_step(self.uid)
        if not step:
            self.edit.setFocus()
            return
        self.edit.clear()
        self.edit.setPlaceholderText("잘했어요! 다음 한 걸음은? " + STEP_HINT)
        self.edit.setFocus()
        self._style(note="'%s' 끝 — 메모에 남김. 다음 한 걸음을 적어 두세요." % step, good=True)
        self._note_timer.start()
        self.finished.emit(self.uid)
        self.changed.emit(self.uid)

    def _style(self, note=None, good=False):
        """진행 중인데 다음 한 걸음이 비어 있으면 눈에 띄게."""
        row = self.store.get(self.uid) if self.uid else None
        empty = not self.edit.text().strip()
        warn = row is not None and row["status"] == ACTIVE and empty and note is None
        border = theme.QUAD[3] if warn else theme.QUAD[2] if good else theme.BORDER
        self.setStyleSheet("#stepBar { background:%s; border:1px solid %s; border-radius:10px; }" % (theme.PANEL, border))
        self.done_btn.setEnabled(not empty)
        if note is None and warn:
            note = "진행 중인데 다음 한 걸음이 비어 있어요."
        self.note.setVisible(bool(note))
        if note:
            self.note.setText(note)
            self.note.setStyleSheet("color:%s;" % (theme.QUAD[2] if good else theme.QUAD[3]))

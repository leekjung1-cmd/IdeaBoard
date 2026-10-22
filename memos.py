"""메모 탭: 아이디어에 대해 떠오르는 생각을 채팅처럼 아래에 적으면 시간순으로 쌓인다.

메모는 고치기·삭제·복사가 되고, 기획서의 어느 칸에 넣거나(뒤에 덧붙임) 새 칸으로 만들 수 있다.
"""
from datetime import datetime

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QTextEdit,
    QToolButton, QVBoxLayout, QWidget,
)

import theme
from brief import AutoText

WEEKDAYS = "월화수목금토일"


def _dt(ms):
    return datetime.fromtimestamp(ms / 1000)


def day_text(d):
    return "%d년 %d월 %d일 (%s)" % (d.year, d.month, d.day, WEEKDAYS[d.weekday()])


def time_text(d):
    h = d.hour
    return "%s %d:%02d" % ("오전" if h < 12 else "오후", (h % 12) or 12, d.minute)


class MemoInput(QTextEdit):
    """Enter = 보내기, Shift+Enter = 줄바꿈. 1~6줄 높이로 늘어남."""
    submit = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setPlaceholderText("떠오른 생각을 적고 Enter  (줄바꿈은 Shift+Enter)")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self._fit()

    def _fit(self, *_):
        extra = self.height() - self.viewport().height()
        line = self.fontMetrics().lineSpacing()
        doc_h = int(self.document().size().height())
        h = min(max(doc_h, line + 8), line * 6 + 8) + extra
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded if doc_h > line * 6 + 8 else Qt.ScrollBarAlwaysOff)
        if h != self.height():
            self.setFixedHeight(h)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._fit()

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Return, Qt.Key_Enter) and not (ev.modifiers() & Qt.ShiftModifier):
            self.submit.emit()
            return
        super().keyPressEvent(ev)


class MemoBubble(QFrame):
    """메모 하나. 오른쪽 위 ⋯ 또는 우클릭으로 메뉴."""
    request = Signal(str, str, object)      # 메모 uuid, 동작, 값

    def __init__(self, row, sections, parent=None):
        super().__init__(parent)
        self.mid = row["uuid"]
        self.body_text = row["body"]
        self.sections = sections        # () -> [(칸 uuid, 제목)]
        self.setObjectName("memo")
        self.setStyleSheet("#memo { background:%s; border:1px solid %s; border-radius:8px; }" % (theme.CHIP, theme.BORDER))

        edited = row["updated_at"] - row["created_at"] > 1000
        self.time = QLabel(time_text(_dt(row["created_at"])) + ("  · 고침" if edited else ""))
        self.time.setStyleSheet("color:%s; background:transparent; border:none;" % theme.TEXT_DIM)
        more = QToolButton()
        more.setText("⋯")
        more.setToolTip("메모 메뉴")
        more.setStyleSheet("QToolButton { padding:0 6px; color:%s; background:transparent; border:none; font-size:13pt; }"
                           % theme.TEXT_DIM)
        more.clicked.connect(lambda: self._menu(more.mapToGlobal(more.rect().bottomLeft())))

        self.struck = bool(row["struck"]) if "struck" in row.keys() else False
        self.body = QLabel(self.body_text)
        self.body.setTextFormat(Qt.PlainText)
        if self.struck:         # 줄 그은 메모: 흐리게 + 가운데 줄
            f = self.body.font()
            f.setStrikeOut(True)
            self.body.setFont(f)
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body.setContextMenuPolicy(Qt.NoContextMenu)     # 우클릭은 이 칸(메모) 메뉴로
        self.body.setStyleSheet("background:transparent; border:none;%s" % (" color:%s;" % theme.TEXT_OFF if self.struck else ""))

        # 고치기용 (평소엔 숨김)
        self.editor = AutoText(min_lines=1)
        self.editor.setTabChangesFocus(False)
        save = QPushButton("저장")
        cancel = QPushButton("취소")
        save.clicked.connect(self._save_edit)
        cancel.clicked.connect(self._cancel_edit)
        self.edit_box = QWidget()
        eb = QVBoxLayout(self.edit_box)
        eb.setContentsMargins(0, 0, 0, 0)
        eb.addWidget(self.editor)
        br = QHBoxLayout()
        br.addStretch(1)
        br.addWidget(cancel)
        br.addWidget(save)
        eb.addLayout(br)
        self.edit_box.hide()

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(self.time)
        head.addStretch(1)
        head.addWidget(more)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 6, 6, 10)
        lay.setSpacing(4)
        lay.addLayout(head)
        lay.addWidget(self.body)
        lay.addWidget(self.edit_box)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda pos: self._menu(self.mapToGlobal(pos)))

    def _menu(self, gpos):
        m = QMenu(self)
        sel = self.body.selectedText()
        m.addAction("선택한 글 복사" if sel else "복사",
                    lambda: QGuiApplication.clipboard().setText(sel or self.body_text))
        m.addAction("줄 풀기" if self.struck else "줄 긋기 (이제 필요 없음)",
                    lambda: self.request.emit(self.mid, "strike", not self.struck))
        m.addAction("고치기", self.start_edit)
        sub = m.addMenu("기획서 칸에 넣기")
        for sid, title in self.sections():
            sub.addAction(title, lambda sid=sid, title=title: self.request.emit(self.mid, "to_section", (sid, title)))
        sub.addSeparator()
        sub.addAction("새 칸으로 만들기", lambda: self.request.emit(self.mid, "new_section", None))
        m.addAction("필요한 기능으로 추가", lambda: self.request.emit(self.mid, "to_feature", None))
        m.addSeparator()
        m.addAction("삭제", lambda: self.request.emit(self.mid, "delete", None))
        m.exec(gpos)

    def start_edit(self):
        self.editor.setPlainText(self.body_text)
        self.body.hide()
        self.edit_box.show()
        self.editor.setFocus()
        c = self.editor.textCursor()
        c.movePosition(c.End)
        self.editor.setTextCursor(c)

    def _cancel_edit(self):
        self.edit_box.hide()
        self.body.show()

    def _save_edit(self):
        text = self.editor.toPlainText().strip()
        if not text:
            return
        self.request.emit(self.mid, "edit", text)


class MemoView(QWidget):
    changed = Signal(str)               # 메모 저장·삭제 (아이디어 uid)
    countChanged = Signal(int)
    sectionFilled = Signal(str, bool)   # 칸 uuid, 새로 만든 칸인지 → 기획서 탭 새로 고침
    featureRequested = Signal(str)      # 메모 글 → 필요한 기능 목록에 추가

    def __init__(self, store_, sections, parent=None):
        super().__init__(parent)
        self.store = store_
        self.sections = sections
        self.uid = None
        self.drafts = {}                # 아이디어별 아직 안 보낸 글

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.input = MemoInput()
        self.input.submit.connect(self.send)
        send = QPushButton("추가")
        send.setToolTip("Enter")
        send.clicked.connect(self.send)
        self.notice = QLabel()
        self.notice.setStyleSheet("color:%s;" % theme.GOOD)
        self.notice.hide()
        self._notice_timer = QTimer(self, singleShot=True, interval=3500)
        self._notice_timer.timeout.connect(self.notice.hide)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self.input, 1)
        row.addWidget(send, 0, Qt.AlignBottom)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(self.scroll, 1)
        lay.addWidget(self.notice)
        lay.addLayout(row)

    # ---------- 읽기 ----------
    def load(self, uid, keep_scroll=False):
        if self.uid and self.uid != uid:
            self.drafts[self.uid] = self.input.toPlainText()
        if self.uid != uid:
            self.input.setPlainText(self.drafts.pop(uid, ""))
        self.uid = uid
        sb = self.scroll.verticalScrollBar()
        pos = sb.value() if keep_scroll else None
        rows = self.store.memos(uid)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(2, 6, 14, 10)
        lay.setSpacing(8)
        lay.addStretch(1)       # 메모가 적으면 아래(입력칸 쪽)에 붙게
        if not rows:
            empty = QLabel("아직 메모가 없어요.\n이 아이디어에 대해 떠오르는 생각을 아래에 적어보세요.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet("color:%s;" % theme.TEXT_DIM)
            lay.addWidget(empty)
            lay.addStretch(1)
        last_day = None
        for r in rows:
            d = _dt(r["created_at"]).date()
            if d != last_day:
                sep = QLabel(day_text(d))
                sep.setAlignment(Qt.AlignCenter)
                sep.setStyleSheet("color:%s; padding-top:6px;" % theme.TEXT_DIM)
                lay.addWidget(sep)
                last_day = d
            b = MemoBubble(r, self.sections)
            b.request.connect(self._on_request)
            lay.addWidget(b)
        self.scroll.setWidget(body)
        QTimer.singleShot(0, lambda: sb.setValue(sb.maximum() if pos is None else pos))
        self.countChanged.emit(len(rows))

    def draft_pending(self):
        return bool(self.input.toPlainText().strip())

    # ---------- 쓰기 ----------
    def send(self):
        text = self.input.toPlainText().strip()
        if not text or not self.uid:
            return
        self.store.add_memo(self.uid, text)
        self.input.clear()
        self.load(self.uid)
        self.changed.emit(self.uid)

    def _flash(self, msg):
        self.notice.setText(msg)
        self.notice.show()
        self._notice_timer.start()

    def _on_request(self, mid, what, value):
        body = next((r["body"] for r in self.store.memos(self.uid) if r["uuid"] == mid), None)
        if body is None:
            return
        if what == "edit":
            self.store.update_memo(mid, value)
            self.load(self.uid, keep_scroll=True)
        elif what == "strike":
            self.store.set_memo_struck(mid, value)
            QTimer.singleShot(0, lambda: self.load(self.uid, keep_scroll=True))
        elif what == "delete":
            if QMessageBox.question(self, "메모 삭제", "이 메모를 삭제할까요?") != QMessageBox.Yes:
                return
            self.store.delete_memo(mid)
            self.load(self.uid, keep_scroll=True)
        elif what == "to_section":
            sid, title = value
            self.store.append_to_section(sid, body)
            self._flash("기획서 '%s' 칸에 넣음" % title)
            self.sectionFilled.emit(sid, False)
        elif what == "to_feature":
            self.featureRequested.emit(body)
            self._flash("'필요한 기능'(필수)에 넣음")
        elif what == "new_section":
            sid = self.store.add_section(self.uid, "")
            self.store.update_section(sid, content=body)
            self.sectionFilled.emit(sid, True)
        self.changed.emit(self.uid)

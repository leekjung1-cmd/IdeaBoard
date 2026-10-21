"""메모함: 모든 아이디어의 메모 + 미분류 메모(빠른 입력 등)를 한 곳에서 최신순으로.

미분류 메모는 맨 위에 눈에 띄게, '아이디어에 넣기' / '새 아이디어로' / 지우기. 체크해서 한꺼번에도.
"""
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea,
    QToolButton, QVBoxLayout, QWidget,
)

import icons
import theme
from memos import MemoInput, _dt, time_text

FILTER_ALL, FILTER_INBOX = "all", "inbox"


def idea_menu(parent, store_, on_pick, exclude=None):
    """아이디어 고르기 메뉴 (진행 중 먼저)."""
    m = QMenu(parent)
    rows = [r for r in store_.ideas() if r["status"] != "완료" and r["uuid"] != exclude]
    rows.sort(key=lambda r: (r["status"] != "진행 중", -r["activity"]))
    for r in rows[:40]:
        m.addAction((r["title"] or "(제목 없음)") + ("   · 진행 중" if r["status"] == "진행 중" else ""),
                    lambda uid=r["uuid"]: on_pick(uid))
    if not rows:
        m.addAction("아이디어가 없어요").setEnabled(False)
    return m


class MemoCard(QFrame):
    request = Signal(str, str, object)      # 메모 uuid, 동작, 값
    checkedChanged = Signal()

    def __init__(self, row, parent=None):
        super().__init__(parent)
        self.mid = row["uuid"]
        self.inbox = row["idea_uuid"] == ""
        self.idea_uuid = row["idea_uuid"]
        self.setObjectName("mcard")
        edge = theme.ACCENT if self.inbox else theme.BORDER
        self.setStyleSheet("#mcard { background:%s; border:1px solid %s; border-left:3px solid %s; border-radius:10px; }"
                           % (theme.PANEL, theme.BORDER, edge))
        self.check = QCheckBox()
        self.check.toggled.connect(lambda _on: self.checkedChanged.emit())
        if self.inbox:
            tag = QLabel("미분류")
            tag.setStyleSheet("color:%s; background:%s; border-radius:9px; padding:1px 8px; font-weight:bold;"
                              % (theme.ON_ACCENT, theme.ACCENT))
        else:
            tag = QPushButton(row["idea_title"] or "(제목 없음)")
            tag.setCursor(Qt.PointingHandCursor)
            tag.setToolTip("이 아이디어 열기")
            tag.setStyleSheet("QPushButton { border:1px solid %s; border-radius:9px; padding:1px 9px; background:transparent; color:%s; }"
                              "QPushButton:hover { border-color:%s; color:%s; }" % (theme.BORDER, theme.TEXT_DIM, theme.ACCENT, theme.TEXT))
            tag.clicked.connect(lambda: self.request.emit(self.mid, "open", self.idea_uuid))
        when = QLabel(_dt(row["created_at"]).strftime("%m/%d ") + time_text(_dt(row["created_at"])))
        when.setStyleSheet("color:%s;" % theme.TEXT_OFF)
        body = QLabel(row["body"])
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setStyleSheet("padding:2px 0;")

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.check)
        top.addWidget(tag)
        top.addWidget(when)
        top.addStretch(1)
        if self.inbox:
            put = QPushButton(" 아이디어에 넣기")
            put.setIcon(icons.icon("step", theme.TEXT_DIM))
            put.clicked.connect(lambda: self.request.emit(self.mid, "pick", put))
            top.addWidget(put)
        more = QToolButton()
        more.setIcon(icons.icon("more", theme.TEXT_DIM))
        more.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(more)
        if self.inbox:
            m.addAction("새 아이디어로 만들기", lambda: self.request.emit(self.mid, "new", None))
        else:
            m.addAction("다른 아이디어로 옮기기…", lambda: self.request.emit(self.mid, "pick", more))
            m.addAction("미분류로 빼기", lambda: self.request.emit(self.mid, "unassign", None))
        m.addSeparator()
        m.addAction("지우기", lambda: self.request.emit(self.mid, "delete", None))
        more.setMenu(m)
        top.addWidget(more)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 10, 10)
        lay.setSpacing(4)
        lay.addLayout(top)
        lay.addWidget(body)


class MemoInboxPage(QWidget):
    changed = Signal()          # 메모가 바뀜 (목록·개수 다시)
    openIdea = Signal(str)

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        title = QLabel("메모함")
        f = title.font()
        f.setPointSize(18)
        f.setBold(True)
        title.setFont(f)
        self.count = QLabel()
        self.count.setStyleSheet("color:%s;" % theme.TEXT_DIM)

        self.input = MemoInput()
        self.input.setPlaceholderText("떠오른 걸 적고 Enter — 미분류 메모로 들어가요 (줄바꿈은 Shift+Enter)")
        self.input.submit.connect(self.add)
        add = QPushButton("추가")
        add.setDefault(True)
        add.clicked.connect(self.add)

        self.filter = QComboBox()
        self.filter.currentIndexChanged.connect(lambda _i: self.refresh())
        self.search = QLineEdit()
        self.search.setPlaceholderText("메모 검색")
        self.search.setClearButtonEnabled(True)
        self._search_timer = QTimer(self, singleShot=True, interval=250)
        self._search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _t: self._search_timer.start())

        # 체크한 것 한꺼번에
        self.bulk = QWidget()
        bl = QHBoxLayout(self.bulk)
        bl.setContentsMargins(0, 0, 0, 0)
        self.bulk_label = QLabel()
        self.bulk_put = QPushButton("아이디어에 넣기 ▾")
        self.bulk_put.clicked.connect(lambda: idea_menu(self, self.store, self._bulk_move).exec(
            self.bulk_put.mapToGlobal(self.bulk_put.rect().bottomLeft())))
        bulk_del = QPushButton("지우기")
        bulk_del.clicked.connect(self._bulk_delete)
        bulk_none = QPushButton("선택 해제")
        bulk_none.clicked.connect(lambda: [c.check.setChecked(False) for c in self.cards])
        for w in (self.bulk_label, self.bulk_put, bulk_del, bulk_none):
            bl.addWidget(w)
        bl.addStretch(1)
        self.bulk.hide()

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cards = []

        head = QHBoxLayout()
        head.addWidget(title)
        head.addSpacing(10)
        head.addWidget(self.count, 1, Qt.AlignBottom)
        inrow = QHBoxLayout()
        inrow.addWidget(self.input, 1)
        inrow.addWidget(add, 0, Qt.AlignBottom)
        frow = QHBoxLayout()
        frow.addWidget(self.filter)
        frow.addWidget(self.search, 1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 20, 28, 16)
        lay.setSpacing(10)
        lay.addLayout(head)
        lay.addLayout(inrow)
        lay.addLayout(frow)
        lay.addWidget(self.bulk)
        lay.addWidget(self.scroll, 1)

    def _fill_filter(self):
        cur = self.filter.currentData()
        self.filter.blockSignals(True)
        self.filter.clear()
        n = self.store.inbox_count()
        self.filter.addItem("전체", FILTER_ALL)
        self.filter.addItem("미분류만 (%d)" % n, FILTER_INBOX)
        for r in self.store.ideas():
            self.filter.addItem("아이디어: " + (r["title"] or "(제목 없음)"), r["uuid"])
        i = self.filter.findData(cur) if cur else 0
        self.filter.setCurrentIndex(max(0, i))
        self.filter.blockSignals(False)

    def show_inbox(self):
        """미분류만 보기로 열기."""
        self._fill_filter()
        self.filter.setCurrentIndex(max(0, self.filter.findData(FILTER_INBOX)))
        self.refresh()

    def refresh(self):
        if self.filter.count() == 0:
            self._fill_filter()
        mode = self.filter.currentData() or FILTER_ALL
        rows = self.store.all_memos(self.search.text())
        if mode == FILTER_INBOX:
            rows = [r for r in rows if r["idea_uuid"] == ""]
        elif mode != FILTER_ALL:
            rows = [r for r in rows if r["idea_uuid"] == mode]
        inbox = [r for r in rows if r["idea_uuid"] == ""]
        rest = [r for r in rows if r["idea_uuid"] != ""]
        pos = self.scroll.verticalScrollBar().value()
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 10, 10)
        lay.setSpacing(8)
        self.cards = []

        def section(text, color):
            lb = QLabel(text)
            lb.setStyleSheet("color:%s; font-weight:bold; padding:8px 2px 0 2px;" % color)
            lay.addWidget(lb)

        if inbox:
            section("미분류  %d  — 나중에 아이디어에 넣어 주세요" % len(inbox), theme.ACCENT)
        for r in inbox:
            self._add_card(lay, r)
        if rest:
            section("아이디어 메모  %d" % len(rest), theme.TEXT_DIM)
        for r in rest:
            self._add_card(lay, r)
        if not rows:
            e = QLabel("메모가 없어요. 위 칸에 적어 보세요." if not self.search.text().strip() else "찾는 메모가 없어요.")
            e.setAlignment(Qt.AlignCenter)
            e.setStyleSheet("color:%s; padding:40px;" % theme.TEXT_DIM)
            lay.addWidget(e)
        lay.addStretch(1)
        self.scroll.setWidget(body)
        QTimer.singleShot(0, lambda: self.scroll.verticalScrollBar().setValue(pos))
        total = len(self.store.all_memos())
        self.count.setText("메모 %d개 · 미분류 %d개" % (total, self.store.inbox_count()))
        self._update_bulk()

    def _add_card(self, lay, r):
        c = MemoCard(r)
        c.request.connect(self._on_request)
        c.checkedChanged.connect(self._update_bulk)
        lay.addWidget(c)
        self.cards.append(c)

    def _picked(self):
        return [c.mid for c in self.cards if c.check.isChecked()]

    def _update_bulk(self):
        n = len(self._picked())
        self.bulk.setVisible(n > 0)
        self.bulk_label.setText("%d개 선택" % n)

    # ---------- 동작 ----------
    def add(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.store.add_memo(self.store.INBOX, text)
        self.input.clear()
        self._done()

    def _on_request(self, mid, what, value):
        if what == "open":
            self.openIdea.emit(value)
            return
        if what == "pick":
            menu = idea_menu(self, self.store, lambda uid: (self.store.move_memos([mid], uid), self._done()))
            menu.exec(value.mapToGlobal(value.rect().bottomLeft()))
            return
        if what == "unassign":
            self.store.move_memos([mid], self.store.INBOX)
        elif what == "new":
            uid = self.store.memo_to_idea(mid)
            self._done()
            self.openIdea.emit(uid)
            return
        elif what == "delete":
            if QMessageBox.question(self, "메모 지우기", "이 메모를 지울까요?") != QMessageBox.Yes:
                return
            self.store.delete_memos([mid])
        self._done()

    def _bulk_move(self, uid):
        self.store.move_memos(self._picked(), uid)
        self._done()

    def _bulk_delete(self):
        ids = self._picked()
        if ids and QMessageBox.question(self, "메모 지우기", "메모 %d개를 지울까요?" % len(ids)) == QMessageBox.Yes:
            self.store.delete_memos(ids)
            self._done()

    def _done(self):
        # 신호 안에서 카드를 지우지 않게 다음 차례에
        QTimer.singleShot(0, lambda: (self._fill_filter(), self.refresh(), self.changed.emit()))

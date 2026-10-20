"""아이디어 보드: 앞으로 만들 앱·프로그램 아이디어를 모으고 우선순위를 정하는 곳.

왼쪽 = 아이디어 목록(클로드 앱의 채팅 목록처럼), 오른쪽 = 대시보드 또는 선택한 아이디어.
"""
import ctypes
import json
import os
import sys

from PySide6.QtCore import (
    QDate, QEvent, QLibraryInfo, QLocale, QObject, QPoint, QRect, QSize, Qt, QTimer, QTranslator, QUrl, Signal,
)
from PySide6.QtGui import (
    QColor, QCursor, QDesktopServices, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap, QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCalendarWidget, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton, QSplitter, QStackedWidget,
    QStyle, QStyledItemDelegate, QTabWidget, QToolButton, QVBoxLayout, QWidget, QWidgetAction,
)

import datadir
import store
import sync
import theme
from version import VERSION
from widgets import DateField
from brief import BriefView
from dashboard import DashboardPage
from devkit import DevView
import focus
from gantt import GanttWindow
import export
from features import FeatureView
from links import LinkButton
from phone import PhoneDialog
from todo import TodoWindow
from memos import MemoView
from store import ACTIVE, QUADRANTS, STATUSES, quadrant

APP_DIR = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
           else os.path.dirname(os.path.abspath(__file__)))
LEGACY_DATA_DIR = os.path.join(APP_DIR, "data")    # 예전 버전(1.0.0 전)은 exe 옆에 저장
DATA_DIR = datadir.default_dir()                    # 지금: %APPDATA%\IdeaBoard (버전 바뀌어도 그대로)

UID = Qt.UserRole
QUAD_ROLE = Qt.UserRole + 1
STATUS_ROLE = Qt.UserRole + 2
CAT_ROLE = Qt.UserRole + 3
DEV_ROLE = Qt.UserRole + 4
PICK_ROLE = Qt.UserRole + 5     # 여러 개 선택 중이면 True/False (체크), 아니면 None

LEVEL_TEXT = {None: "미정", 1: "1 · 매우 낮음", 2: "2 · 낮음", 3: "3 · 보통", 4: "4 · 높음", 5: "5 · 매우 높음"}


def make_icon():
    """2×2 사분면 모양 아이콘."""
    pm = QPixmap(256, 256)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    gap, pad = 14, 12
    s = (256 - pad * 2 - gap) // 2
    for i, q in enumerate((1, 2, 3, 4)):
        x = pad + (i % 2) * (s + gap)
        y = pad + (i // 2) * (s + gap)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.QUAD[q]))
        p.drawRoundedRect(x, y, s, s, 22, 22)
    p.end()
    return pm


def quad_badge_style(q):
    c = QColor(theme.QUAD[q])
    return ("QLabel {{ color:{fg}; background:rgba({r},{g},{b},40); border:1px solid rgba({r},{g},{b},140);"
            " border-radius:10px; padding:2px 10px; }}").format(
        fg=theme.QUAD[q] if q else theme.TEXT_DIM, r=c.red(), g=c.green(), b=c.blue())


# ---------------------------------------------------------------- 작은 입력 위젯

class LevelCombo(QComboBox):
    """중요도·긴급도 1~5 (미정 가능)."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        for v in (None, 1, 2, 3, 4, 5):
            self.addItem(LEVEL_TEXT[v], v)
        self.currentIndexChanged.connect(lambda _i: self.changed.emit())

    def value(self):
        return self.currentData()

    def setValue(self, v):
        self.setCurrentIndex(max(0, self.findData(v)))


class StatusCombo(QComboBox):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.addItems(STATUSES)
        self.currentIndexChanged.connect(lambda _i: self.changed.emit())

    def value(self):
        return self.currentText()

    def setValue(self, v):
        i = self.findText(v or STATUSES[0])
        self.setCurrentIndex(max(0, i))


class CategoryCombo(QComboBox):
    """용도: 목록에서 고르거나 직접 입력 (빈칸 = 안 정함)."""
    changed = Signal()

    def __init__(self, categories=(), parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.lineEdit().setPlaceholderText("용도 (직접 입력 가능)")
        self.setMinimumWidth(130)
        self._last = ""
        self.set_items(categories)
        self.activated.connect(lambda _i: self._typed())
        self.lineEdit().editingFinished.connect(self._typed)

    def set_items(self, categories):
        cur = self.currentText()
        self.blockSignals(True)
        self.clear()
        self.addItem("")
        self.addItems(list(categories))
        self.setEditText(cur)
        self.blockSignals(False)

    def _typed(self):
        if self.value() != self._last:
            self._last = self.value()
            self.changed.emit()

    def value(self):
        return self.currentText().strip()

    def setValue(self, v):
        self.blockSignals(True)
        self.setEditText(v or "")
        self.blockSignals(False)
        self._last = v or ""


# ---------------------------------------------------------------- 새 아이디어 창

class NewIdeaDialog(QDialog):
    def __init__(self, categories=(), parent=None):
        super().__init__(parent)
        self.setWindowTitle("새로운 아이디어")
        self.setMinimumWidth(460)
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.title = QLineEdit()
        self.title.setPlaceholderText("예: 러닝 케이던스 메트로놈")
        self.summary = QLineEdit()
        self.summary.setPlaceholderText("어떤 건지 한 줄로")
        self.status = StatusCombo()
        self.category = CategoryCombo(categories)
        self.importance = LevelCombo()
        self.urgency = LevelCombo()
        self.start = DateField()
        self.due = DateField()
        self.start.setValue(QDate.currentDate().toString("yyyy-MM-dd"))    # 시작일은 기본 오늘
        form.addRow("제목", self.title)
        form.addRow("한 줄 요약", self.summary)
        form.addRow("용도", self.category)
        form.addRow("상태", self.status)
        form.addRow("중요도", self.importance)
        form.addRow("긴급도", self.urgency)
        form.addRow("시작 예정일", self.start)
        form.addRow("목표 완료일", self.due)
        self.next_step = QLineEdit()
        self.next_step.setPlaceholderText("30분 안에 끝낼 다음 행동 1개 (나중에 적어도 돼요)")
        form.addRow("👣 다음 한 걸음", self.next_step)
        self.dev = QCheckBox("💻  개발할 앱·프로그램이에요")
        self.dev.setToolTip("켜면 '개발' 탭(만드는 순서 · 클로드에게 부탁하기 · 개발 폴더 만들기)과\n"
                            "기능마다 '확인하는 법' 칸이 생겨요. 나중에 아이디어 화면에서 켜고 꺼도 돼요.")
        form.addRow("", self.dev)

        hint = QLabel("중요도·긴급도가 %d 이상이면 '높음'으로 보고 대시보드 4분면에 놓아요.\n"
                      "잘 모르겠으면 '미정'으로 두고 나중에 정해도 돼요.\n"
                      "'진행 중'은 %d개까지만 둘 수 있어요. 새 아이디어는 보통 '보관함'에 넣어 두세요."
                      % (store.HIGH, store.ACTIVE_LIMIT))
        hint.setStyleSheet("color:%s;" % theme.TEXT_DIM)
        hint.setWordWrap(True)

        buttons = QDialogButtonBox()
        self.ok = buttons.addButton("만들기", QDialogButtonBox.AcceptRole)
        buttons.addButton("취소", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok.setEnabled(False)
        self.ok.setDefault(True)
        self.title.textChanged.connect(lambda t: self.ok.setEnabled(bool(t.strip())))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.addLayout(form)
        lay.addSpacing(6)
        lay.addWidget(hint)
        lay.addSpacing(8)
        lay.addWidget(buttons)

    def values(self):
        return dict(title=self.title.text().strip(), summary=self.summary.text().strip(),
                    status=self.status.value(), category=self.category.value(),
                    importance=self.importance.value(),
                    urgency=self.urgency.value(), start_date=self.start.value(),
                    due_date=self.due.value(), dev=1 if self.dev.isChecked() else 0,
                    next_step=self.next_step.text().strip())


# ---------------------------------------------------------------- 왼쪽 목록

class IdeaDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 34)

    def paint(self, p, option, index):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = option.rect.adjusted(6, 1, -6, -1)
        if option.state & QStyle.State_Selected:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.ITEM_SEL))
            p.drawRoundedRect(r, 6, 6)
        elif option.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.ITEM_HOVER))
            p.drawRoundedRect(r, 6, 6)

        q = index.data(QUAD_ROLE) or 0
        status = index.data(STATUS_ROLE) or ""
        pick = index.data(PICK_ROLE)
        x0 = r.left() + 10
        if pick is not None:        # 여러 개 선택 중: 체크칸
            if pick and not option.state & QStyle.State_MouseOver:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(theme.ITEM_SEL))
                p.drawRoundedRect(r, 6, 6)
            box = QRect(x0, r.center().y() - 7, 14, 14)
            p.setPen(QPen(QColor(theme.ACCENT if pick else theme.TEXT_DIM), 1.4))
            p.setBrush(QColor(theme.ACCENT) if pick else Qt.NoBrush)
            p.drawRoundedRect(box, 3, 3)
            if pick:
                p.setPen(QPen(QColor("white"), 2))
                p.drawLine(box.left() + 3, box.center().y(), box.left() + 6, box.bottom() - 3)
                p.drawLine(box.left() + 6, box.bottom() - 3, box.right() - 3, box.top() + 3)
            x0 = box.right() + 9
        dot = QRect(x0, r.center().y() - 4, 9, 9)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.QUAD[q]))
        if q:
            p.drawEllipse(dot)
        else:
            p.setBrush(Qt.NoBrush)
            p.setPen(QColor(theme.QUAD[0]))
            p.drawEllipse(dot.adjusted(0, 0, -1, -1))

        fm = option.fontMetrics
        right = r.right() - 10
        if status and status != STATUSES[0]:
            sw = fm.horizontalAdvance(status)
            p.setPen(QColor(theme.ACCENT if status == ACTIVE else theme.TEXT_DIM))
            p.drawText(QRect(right - sw, r.top(), sw, r.height()), Qt.AlignVCenter | Qt.AlignRight, status)
            right -= sw + 10
        cat = index.data(CAT_ROLE) or ""
        if cat:     # 용도: 작은 테두리 꼬리표
            cw = fm.horizontalAdvance(cat) + 12
            tag = QRect(right - cw, r.center().y() - 9, cw, 18)
            p.setPen(QPen(QColor(theme.BORDER), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(tag, 9, 9)
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(tag, Qt.AlignCenter, cat)
            right -= cw + 8

        title = index.data(Qt.DisplayRole) or "(제목 없음)"
        left = dot.right() + 10
        if index.data(DEV_ROLE):    # 개발 프로젝트 표시
            p.setPen(QColor(theme.TEXT_DIM))
            ew = fm.horizontalAdvance("💻") + 4
            p.drawText(QRect(left, r.top(), ew, r.height()), Qt.AlignVCenter | Qt.AlignLeft, "💻")
            left += ew + 2
        tr = QRect(left, r.top(), right - left, r.height())
        done = status in ("완료", "보류")
        p.setPen(QColor(theme.TEXT_DIM if done else theme.TEXT))
        p.drawText(tr, Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(title, Qt.ElideRight, tr.width()))
        p.restore()


class Sidebar(QWidget):
    newRequested = Signal()
    dashboardRequested = Signal()
    ganttRequested = Signal()
    todosRequested = Signal()
    appAction = Signal(str)
    ideaSelected = Signal(str)
    bulkStatus = Signal(list, str)      # 아이디어 uuid 들, 바꿀 상태
    bulkDelete = Signal(list)
    viewChanged = Signal()

    LONG_PRESS_MS = 550

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            #sidebar {{ background:{bg}; }}
            #sidebar QListWidget {{ background:{bg}; border:none; outline:none; }}
            #sideBtn {{ text-align:left; padding:8px 12px; border:none; border-radius:6px; background:transparent; }}
            #sideBtn:hover {{ background:{hover}; }}
            #sideBtn:checked {{ background:{sel}; }}
            #newBtn {{ text-align:left; padding:8px 12px; border-radius:6px; background:{panel};
                       border:1px solid {border}; font-weight:bold; }}
            #newBtn:hover {{ background:{hover}; border-color:{accent}; }}
            #sectionLabel {{ color:{dim}; padding:10px 14px 4px 14px; }}
        """.format(bg=theme.SIDEBAR, hover=theme.ITEM_HOVER, sel=theme.ITEM_SEL, panel=theme.PANEL,
                   border=theme.BORDER, accent=theme.ACCENT, dim=theme.TEXT_DIM))

        name = QLabel("아이디어 보드")
        f = name.font()
        f.setPointSize(13)
        f.setBold(True)
        name.setFont(f)
        name.setContentsMargins(8, 4, 0, 6)

        self.app_menu_btn = QToolButton()
        self.app_menu_btn.setText("⋯")
        self.app_menu_btn.setToolTip("내보내기 · 백업")
        self.app_menu_btn.setPopupMode(QToolButton.InstantPopup)
        self.app_menu_btn.setStyleSheet("QToolButton { font-size:14pt; padding:0 8px; color:%s; } "
                                        "QToolButton::menu-indicator { image:none; }" % theme.TEXT_DIM)
        am = QMenu(self.app_menu_btn)
        am.addSection("아이디어 보드 v%s" % VERSION)
        am.addAction("모든 아이디어 내보내기 (마크다운)…", lambda: self.appAction.emit("export_all"))
        am.addAction("백업 파일 만들기…", lambda: self.appAction.emit("backup"))
        am.addAction("폰 연결 (와이파이 동기화)…", lambda: self.appAction.emit("phone"))
        am.addSeparator()
        am.addAction("예전 데이터·백업 가져오기 (합치기)…", lambda: self.appAction.emit("import"))
        am.addSeparator()
        am.addAction("데이터 폴더 열기", lambda: self.appAction.emit("data_dir"))
        self.app_menu_btn.setMenu(am)

        self.new_btn = QPushButton("＋  새로운 아이디어")
        self.new_btn.setObjectName("newBtn")
        self.new_btn.setToolTip("Ctrl+N")
        self.new_btn.clicked.connect(self.newRequested)

        self.dash_btn = QPushButton("▦  대시보드")
        self.dash_btn.setObjectName("sideBtn")
        self.dash_btn.setCheckable(True)
        self.dash_btn.clicked.connect(self.dashboardRequested)

        self.gantt_btn = QPushButton("▤  일정표")
        self.gantt_btn.setObjectName("sideBtn")
        self.gantt_btn.setToolTip("시작일→목표일을 달력 위 막대로 보기 (Ctrl+T)")
        self.gantt_btn.clicked.connect(self.ganttRequested)

        self.todo_btn = QPushButton()
        self.todo_btn.setObjectName("sideBtn")
        self.todo_btn.setToolTip("할일을 포스트잇 벽으로 보기 (Ctrl+Shift+T)")
        self.todo_btn.clicked.connect(self.todosRequested)
        self.set_todo_count(0)

        self.search = QLineEdit()
        self.search.setPlaceholderText("검색 (제목·기획서·메모)")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _t: self.refresh(self.current()))

        self.section = QLabel()
        self.section.setObjectName("sectionLabel")

        # 보기: 상태 필터 + 정렬 (설정에 저장)
        self.hidden = set()             # 목록에서 숨길 상태
        self.hidden_cats = set()        # 목록에서 숨길 용도 ('' = 용도 없음)
        self.dev_only = False           # 개발 프로젝트만 보기
        self.sort_mode = "recent"
        self.view_btn = QToolButton()
        self.view_btn.setText("보기 ▾")
        self.view_btn.setToolTip("상태 필터 · 정렬")
        self.view_btn.setPopupMode(QToolButton.InstantPopup)
        self.view_btn.setStyleSheet("QToolButton { color:%s; padding:2px 6px; } "
                                    "QToolButton::menu-indicator { image:none; }" % theme.TEXT_DIM)
        self.view_menu = QMenu(self.view_btn)
        self.view_menu.aboutToShow.connect(self._build_view_menu)
        self.view_btn.setMenu(self.view_menu)

        self.list = QListWidget()
        self.list.setItemDelegate(IdeaDelegate(self.list))
        self.list.setMouseTracking(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.currentItemChanged.connect(self._current_changed)
        self.list.itemClicked.connect(self._clicked)

        # 여러 개 선택: 길게 누르거나 오른쪽 클릭 → '여러 개 선택'. 체크한 것들을 한꺼번에 상태 바꾸기·삭제
        self.shown = None               # 오른쪽에 열려 있는 아이디어
        self.picking = False
        self.picked = set()
        self._swallow_click = False
        self._press = None
        self._press_timer = QTimer(self, singleShot=True, interval=self.LONG_PRESS_MS)
        self._press_timer.timeout.connect(self._long_pressed)
        self.list.viewport().installEventFilter(self)
        self.pick_bar = QWidget()
        self.pick_bar.setObjectName("pickBar")
        self.pick_bar.setAttribute(Qt.WA_StyledBackground, True)
        self.pick_bar.setStyleSheet("#pickBar { background:%s; border:1px solid %s; border-radius:8px; }"
                                    % (theme.PANEL, theme.ACCENT))
        pb = QVBoxLayout(self.pick_bar)
        pb.setContentsMargins(8, 6, 8, 6)
        pb.setSpacing(4)
        self.pick_label = QLabel()
        pick_btns = QHBoxLayout()
        pick_btns.setSpacing(4)
        self.pick_status = QToolButton()
        self.pick_status.setText("상태 ▾")
        self.pick_status.setToolTip("체크한 아이디어의 상태를 한꺼번에 바꾸기")
        self.pick_status.setPopupMode(QToolButton.InstantPopup)
        self.pick_status.setStyleSheet("QToolButton::menu-indicator { image:none; }")
        sm = QMenu(self.pick_status)
        for st in STATUSES:
            sm.addAction(st, lambda st=st: self.picked and self.bulkStatus.emit(sorted(self.picked), st))
        self.pick_status.setMenu(sm)
        self.pick_del = QPushButton("삭제")
        self.pick_del.clicked.connect(lambda: self.picked and self.bulkDelete.emit(sorted(self.picked)))
        self.pick_all = QPushButton("전체")
        self.pick_all.setToolTip("보이는 것 전부 체크 / 해제")
        self.pick_all.clicked.connect(self._pick_all)
        pick_cancel = QPushButton("취소")
        pick_cancel.setToolTip("선택 끝내기 (Esc)")
        pick_cancel.clicked.connect(lambda: self.end_pick())
        for b in (self.pick_status, self.pick_del, self.pick_all, pick_cancel):
            pick_btns.addWidget(b)
        pb.addWidget(self.pick_label)
        pb.addLayout(pick_btns)
        self.pick_bar.hide()
        esc = QShortcut(QKeySequence(Qt.Key_Escape), self, lambda: self.picking and self.end_pick())
        esc.setContext(Qt.WidgetWithChildrenShortcut)

        top = QVBoxLayout()
        top.setContentsMargins(10, 12, 10, 4)
        top.setSpacing(6)
        name_row = QHBoxLayout()
        name_row.addWidget(name, 1)
        name_row.addWidget(self.app_menu_btn)
        top.addLayout(name_row)
        top.addWidget(self.new_btn)
        top.addWidget(self.dash_btn)
        top.addWidget(self.gantt_btn)
        top.addWidget(self.todo_btn)
        top.addSpacing(4)
        top.addWidget(self.search)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(0)
        sec = QHBoxLayout()
        sec.setContentsMargins(0, 0, 8, 0)
        sec.addWidget(self.section, 1)
        sec.addWidget(self.view_btn, 0, Qt.AlignBottom)
        lay.addLayout(top)
        lay.addLayout(sec)
        pick_wrap = QHBoxLayout()
        pick_wrap.setContentsMargins(8, 2, 8, 4)
        pick_wrap.addWidget(self.pick_bar)
        lay.addLayout(pick_wrap)
        lay.addWidget(self.list, 1)
        ver = QLabel("v%s" % VERSION)
        ver.setStyleSheet("color:%s; padding:2px 14px;" % theme.TEXT_OFF)
        ver.setToolTip("아이디어 보드 버전")
        lay.addWidget(ver)

    def set_todo_count(self, n):
        self.todo_btn.setText("☑  할일" + ("   %d" % n if n else ""))

    def current(self):
        it = self.list.currentItem()
        return it.data(UID) if it else None

    def refresh(self, select=None):
        """목록 다시 읽기. select 가 있으면 그 아이디어를 (신호 없이) 선택 상태로."""
        all_rows = self.store.ideas(self.search.text())
        rows = self._sorted([r for r in all_rows if r["status"] not in self.hidden
                             and r["category"] not in self.hidden_cats and (r["dev"] or not self.dev_only)])
        if self.picking:
            self.picked &= {r["uuid"] for r in rows}
        self.list.blockSignals(True)
        self.list.clear()
        sel_item = None
        for r in rows:
            it = QListWidgetItem(r["title"])
            it.setData(UID, r["uuid"])
            it.setData(QUAD_ROLE, quadrant(r["importance"], r["urgency"]))
            it.setData(STATUS_ROLE, r["status"])
            it.setData(CAT_ROLE, r["category"])
            it.setData(DEV_ROLE, bool(r["dev"]))
            it.setData(PICK_ROLE, (r["uuid"] in self.picked) if self.picking else None)
            it.setToolTip((r["title"] or "") + ("\n" + r["summary"] if r["summary"] else ""))
            self.list.addItem(it)
            if r["uuid"] == select:
                sel_item = it
        if sel_item:
            self.list.setCurrentItem(sel_item)
        else:
            self.list.setCurrentRow(-1)
        self.list.blockSignals(False)
        found = "검색 결과 %d개" if self.search.text().strip() else "아이디어 %d개"
        text = found % len(rows)
        if len(rows) != len(all_rows):
            text += "  (%d개 숨김)" % (len(all_rows) - len(rows))
        self.section.setText(text)
        self._update_pick_bar()
        active = bool(self.hidden or self.hidden_cats or self.dev_only) or self.sort_mode != "recent"
        self.view_btn.setStyleSheet("QToolButton { color:%s; padding:2px 6px; } "
                                    "QToolButton::menu-indicator { image:none; }"
                                    % (theme.ACCENT if active else theme.TEXT_DIM))

    SORTS = (("recent", "최근 활동순"), ("priority", "우선순위순 (지금 할 것 먼저)"), ("due", "목표일순"))

    def _sorted(self, rows):
        if self.sort_mode == "priority":
            order = {1: 0, 2: 1, 3: 2, 4: 3, 0: 4}
            return sorted(rows, key=lambda r: (order[quadrant(r["importance"], r["urgency"])],
                                               -((r["importance"] or 0) + (r["urgency"] or 0)),
                                               r["due_date"] or "9999"))
        if self.sort_mode == "due":
            return sorted(rows, key=lambda r: (r["due_date"] is None, r["due_date"] or "", -r["activity"]))
        return rows     # store 가 이미 최근 활동순

    def _build_view_menu(self):
        m = self.view_menu
        m.clear()
        m.addSection("상태")
        for st in STATUSES:
            a = m.addAction(st)
            a.setCheckable(True)
            a.setChecked(st not in self.hidden)
            a.toggled.connect(lambda on, st=st: self._toggle_status(st, on))
        m.addAction("모두 보기", lambda: self._set_view(hidden=set(), hidden_cats=set(), dev_only=False))
        m.addAction("완료·보류 숨기기", lambda: self._set_view(hidden={"완료", "보류"}))
        m.addSection("용도")
        for cat in self.store.categories() + [""]:
            a = m.addAction(cat or "(용도 없음)")
            a.setCheckable(True)
            a.setChecked(cat not in self.hidden_cats)
            a.toggled.connect(lambda on, cat=cat: self._toggle_cat(cat, on))
        m.addSection("종류")
        a = m.addAction("💻 개발 프로젝트만")
        a.setCheckable(True)
        a.setChecked(self.dev_only)
        a.toggled.connect(lambda on: self._set_view(dev_only=on))
        m.addSection("정렬")
        for key, label in self.SORTS:
            a = m.addAction(label)
            a.setCheckable(True)
            a.setChecked(key == self.sort_mode)
            a.triggered.connect(lambda _c=False, key=key: self._set_view(sort_mode=key))

    def _toggle_status(self, st, on):
        hidden = set(self.hidden)
        (hidden.discard if on else hidden.add)(st)
        self._set_view(hidden=hidden)

    def _toggle_cat(self, cat, on):
        cats = set(self.hidden_cats)
        (cats.discard if on else cats.add)(cat)
        self._set_view(hidden_cats=cats)

    def _set_view(self, hidden=None, sort_mode=None, hidden_cats=None, dev_only=None):
        if dev_only is not None:
            self.dev_only = bool(dev_only)
        if hidden is not None:
            self.hidden = set(hidden)
        if hidden_cats is not None:
            self.hidden_cats = set(hidden_cats)
        if sort_mode is not None:
            self.sort_mode = sort_mode
        self.refresh(self.current())
        self.viewChanged.emit()

    def view_state(self):
        return {"hidden": sorted(self.hidden), "hidden_cats": sorted(self.hidden_cats), "sort": self.sort_mode,
                "dev_only": self.dev_only}

    def set_view_state(self, st):
        self.hidden = set(st.get("hidden", [])) & set(STATUSES)
        self.sort_mode = st.get("sort", "recent") if st.get("sort") in dict(self.SORTS) else "recent"
        self.hidden_cats = set(st.get("hidden_cats", []))
        self.dev_only = bool(st.get("dev_only", False))

    def select(self, uid):
        """uid 선택 (None 이면 선택 해제). 신호는 안 보냄."""
        self.shown = uid
        self.list.blockSignals(True)
        self.list.setCurrentRow(-1)
        for i in range(self.list.count()):
            if self.list.item(i).data(UID) == uid:
                self.list.setCurrentRow(i)
                break
        self.list.blockSignals(False)
        self.dash_btn.setChecked(uid is None)

    def _current_changed(self, cur, _prev):
        if cur is not None and not self.picking:
            self.dash_btn.setChecked(False)
            self.shown = cur.data(UID)
            self.ideaSelected.emit(self.shown)

    def _menu(self, pos):
        it = self.list.itemAt(pos)
        if not it:
            return
        uid = it.data(UID)
        uids = sorted(self.picked) if self.picking and uid in self.picked else [uid]
        many = " (%d개)" % len(uids) if len(uids) > 1 else ""
        m = QMenu(self)
        sub = m.addMenu("상태 바꾸기" + many)
        cur = it.data(STATUS_ROLE)
        for st in STATUSES:
            a = sub.addAction(st, lambda st=st: self.bulkStatus.emit(uids, st))
            if len(uids) == 1 and st == cur:
                a.setCheckable(True)
                a.setChecked(True)
        if not self.picking:
            m.addAction("여러 개 선택 (체크해서 한꺼번에)", lambda: self.start_pick(uid))
        m.addSeparator()
        m.addAction("삭제" + many, lambda: self.bulkDelete.emit(uids))
        m.exec(self.list.viewport().mapToGlobal(pos))

    # ---------- 여러 개 선택 ----------
    def eventFilter(self, obj, ev):
        if obj is self.list.viewport():
            t = ev.type()
            if t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
                self._press = ev.position().toPoint()
                self._press_timer.start()
            elif t == QEvent.MouseMove and self._press is not None:
                if (ev.position().toPoint() - self._press).manhattanLength() > 8:
                    self._press_timer.stop()
                    self._press = None
            elif t in (QEvent.MouseButtonRelease, QEvent.Leave):
                self._press_timer.stop()
                self._press = None
                if self._swallow_click:     # 손 뗄 때 클릭 신호가 안 오는 경우도 있어서 이번 차례가 끝나면 풀기
                    QTimer.singleShot(0, lambda: setattr(self, "_swallow_click", False))
        return super().eventFilter(obj, ev)

    def _long_pressed(self):
        it = self.list.itemAt(self._press) if self._press is not None else None
        self._press = None
        if it is None:
            return
        uid = it.data(UID)
        if self.picking:
            self._toggle_pick(uid)
        else:
            self.start_pick(uid)
        self._swallow_click = True      # 손을 뗄 때 오는 클릭은 무시

    def start_pick(self, uid=None):
        self.picking = True
        self.picked = {uid} if uid else set()
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.pick_bar.show()
        self.refresh(self.shown)

    def end_pick(self):
        if not self.picking:
            return
        self.picking = False
        self.picked = set()
        self._swallow_click = False
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.pick_bar.hide()
        self.refresh(self.shown)

    def _clicked(self, it):
        if not self.picking:
            return
        if self._swallow_click:
            self._swallow_click = False
            return
        self._toggle_pick(it.data(UID))

    def _toggle_pick(self, uid):
        (self.picked.discard if uid in self.picked else self.picked.add)(uid)
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(UID) == uid:
                it.setData(PICK_ROLE, uid in self.picked)
        self._update_pick_bar()

    def _pick_all(self):
        uids = {self.list.item(i).data(UID) for i in range(self.list.count())}
        self.picked = set() if uids and uids <= self.picked else uids
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setData(PICK_ROLE, it.data(UID) in self.picked)
        self._update_pick_bar()

    def _update_pick_bar(self):
        if not self.picking:
            return
        n = len(self.picked)
        self.pick_label.setText("%d개 선택  —  누르면 체크 / 해제" % n if n else "체크할 아이디어를 누르세요")
        self.pick_status.setEnabled(bool(n))
        self.pick_del.setEnabled(bool(n))


# ---------------------------------------------------------------- 오른쪽: 아이디어

class IdeaPage(QWidget):
    changed = Signal(str)        # 저장했음 (uid)
    deleteRequested = Signal(str)

    def __init__(self, store_, data_dir, parent=None):
        super().__init__(parent)
        self.store = store_
        self.uid = None
        self._loading = False

        self.title = QLineEdit()
        self.title.setPlaceholderText("제목")
        f = self.title.font()
        f.setPointSize(18)
        f.setBold(True)
        self.title.setFont(f)
        self.title.setStyleSheet("QLineEdit { border:1px solid transparent; background:transparent; padding:2px 4px; }"
                                 "QLineEdit:hover { border-color:%s; } QLineEdit:focus { border-color:%s; }"
                                 % (theme.BORDER, theme.ACCENT))
        self.summary = QLineEdit()
        self.summary.setPlaceholderText("한 줄 요약")
        self.summary.setStyleSheet("QLineEdit { border:1px solid transparent; background:transparent; padding:2px 4px;"
                                   " color:%s; } QLineEdit:hover { border-color:%s; }"
                                   " QLineEdit:focus { border-color:%s; color:%s; }"
                                   % (theme.TEXT_DIM, theme.BORDER, theme.ACCENT, theme.TEXT))

        more = QToolButton()
        more.setText("⋯")
        more.setToolTip("더 보기")
        more.setPopupMode(QToolButton.InstantPopup)
        mm = QMenu(more)
        mm.addAction("클로드로 보내기 (복사 + 클로드 열기)", lambda: self._export("claude"))
        mm.addAction("내용 복사 (마크다운)", lambda: self._export("copy"))
        mm.addAction("마크다운 파일로 내보내기…", lambda: self._export("file"))
        mm.addSeparator()
        mm.addAction("이 아이디어 삭제", lambda: self.uid and self.deleteRequested.emit(self.uid))
        more.setMenu(mm)
        more.setStyleSheet("QToolButton { font-size:16pt; padding:0 8px; } QToolButton::menu-indicator { image:none; }")

        self.link_btn = LinkButton(self.store)
        self.link_btn.changed.connect(self.changed)

        self.dev_btn = QToolButton()
        self.dev_btn.setText("💻 개발")
        self.dev_btn.setCheckable(True)
        self.dev_btn.setToolTip("개발할 앱·프로그램이면 켜요.\n"
                                "'개발' 탭(만드는 순서 · 클로드에게 부탁하기 · 개발 폴더 만들기)과\n"
                                "기능마다 '확인하는 법' 칸이 생겨요. 꺼도 적어 둔 내용은 그대로 있어요.")
        self.dev_btn.setStyleSheet(
            "QToolButton { padding:4px 10px; border:1px solid %s; border-radius:12px; color:%s; }"
            "QToolButton:hover { border-color:%s; }"
            "QToolButton:checked { background:%s; border-color:%s; color:%s; }"
            % (theme.BORDER, theme.TEXT_DIM, theme.ACCENT, theme.ITEM_SEL, theme.ACCENT, theme.TEXT))
        self.dev_btn.toggled.connect(self._toggle_dev)

        head = QHBoxLayout()
        head.addWidget(self.title, 1)
        head.addWidget(self.dev_btn, 0, Qt.AlignVCenter)
        head.addWidget(self.link_btn, 0, Qt.AlignVCenter)
        head.addWidget(more, 0, Qt.AlignTop)

        self.status = StatusCombo()
        self.category = CategoryCombo(self.store.categories())
        self.importance = LevelCombo()
        self.urgency = LevelCombo()
        self.start = DateField()
        self.due = DateField()
        self.badge = QLabel()
        self.step = focus.NextStepBar(self.store)
        self.step.changed.connect(self.changed)
        self.step.finished.connect(lambda uid: self.memos.load(uid))

        # 두 줄: 상태·중요도·긴급도(+사분면) / 일정
        meta = QGridLayout()
        meta.setHorizontalSpacing(8)
        meta.setVerticalSpacing(6)
        cells = ((0, 0, "상태", self.status), (0, 2, "중요도", self.importance), (0, 4, "긴급도", self.urgency),
                 (1, 0, "시작", self.start), (1, 2, "목표", self.due), (1, 4, "용도", self.category))
        for r, c, label, w in cells:
            lb = QLabel(label)
            lb.setStyleSheet("color:%s;" % theme.TEXT_DIM)
            meta.addWidget(lb, r, c)
            meta.addWidget(w, r, c + 1)
        meta.addWidget(self.badge, 0, 6)
        meta.setColumnStretch(7, 1)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.brief = BriefView(self.store)
        self.brief.changed.connect(self.changed)
        self.brief.edited.connect(self._update_progress)
        self.tabs.addTab(self.brief, "기획서")
        self.features = FeatureView(self.store)
        self.features.changed.connect(self.changed)
        self.features.countChanged.connect(
            lambda d, n: self.tabs.setTabText(self.tabs.indexOf(self.features),
                                              "필요한 기능  %d/%d" % (d, n) if n else "필요한 기능"))
        self.tabs.addTab(self.features, "필요한 기능")
        self.devview = DevView(self.store, data_dir)
        self.devview.changed.connect(self._dev_changed)
        self.features.changed.connect(lambda _u: self.devview.refresh())
        self.tabs.addTab(self.devview, "💻 개발")
        self.memos = MemoView(self.store, self.brief.section_titles)
        self.memos.changed.connect(self.changed)
        self.memos.countChanged.connect(
            lambda n: self.tabs.setTabText(self.tabs.indexOf(self.memos), "메모  %d" % n if n else "메모"))
        self.memos.sectionFilled.connect(self._section_filled)
        self.memos.featureRequested.connect(self.features.add_text)
        self.tabs.addTab(self.memos, "메모")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 20, 28, 16)
        lay.setSpacing(6)
        lay.addLayout(head)
        lay.addWidget(self.summary)
        lay.addSpacing(6)
        lay.addLayout(meta)
        lay.addSpacing(8)
        lay.addWidget(self.step)
        lay.addSpacing(6)
        lay.addWidget(self.tabs, 1)

        # 글자는 멈추고 0.5초 뒤 저장, 나머지는 바로 저장
        self._timer = QTimer(self, singleShot=True, interval=500)
        self._timer.timeout.connect(self.flush)
        for w in (self.title, self.summary):
            w.textEdited.connect(lambda _t: self._timer.start())
            w.editingFinished.connect(self.flush)
        self.summary.textChanged.connect(self._update_progress)
        for w in (self.status, self.category, self.importance, self.urgency, self.start, self.due):
            w.changed.connect(self._save_meta)

    def load(self, uid):
        self.flush()
        row = self.store.get(uid)
        if row is None:
            self.uid = None
            return False
        self._loading = True
        self.uid = uid
        self.title.setText(row["title"])
        self.summary.setText(row["summary"])
        self.status.setValue(row["status"])
        self.category.set_items(self.store.categories())
        self.category.setValue(row["category"])
        self.importance.setValue(row["importance"])
        self.urgency.setValue(row["urgency"])
        self.start.setValue(row["start_date"])
        self.due.setValue(row["due_date"])
        dev = bool(row["dev"])
        self.dev_btn.setChecked(dev)
        self.tabs.setTabVisible(self.tabs.indexOf(self.devview), dev)
        if not dev and self.tabs.currentWidget() is self.devview:
            self.tabs.setCurrentWidget(self.brief)
        self.features.set_dev(dev)
        self.devview.load(uid)
        self.brief.load(uid)
        self.features.load(uid)
        self.memos.load(uid)
        self.link_btn.load(uid)
        self.step.load(uid)
        self._loading = False
        self._update_badge()
        self._update_progress()
        self.title.setCursorPosition(0)
        self.summary.setCursorPosition(0)
        return True

    def flush(self):
        """글자 저장 대기 중이면 지금 저장."""
        self._timer.stop()
        if self._loading or not self.uid:
            return
        self.brief.flush()
        self.step.flush()
        row = self.store.get(self.uid)
        if row is None:
            return
        t, s = self.title.text().strip(), self.summary.text().strip()
        if t != row["title"] or s != row["summary"]:
            self.store.update(self.uid, title=t, summary=s)
            self.changed.emit(self.uid)

    def _save_meta(self):
        if self._loading or not self.uid:
            return
        before = self.store.get(self.uid)["status"]
        if self.status.value() == ACTIVE and before != ACTIVE and not focus.ensure_room(self, self.store, [self.uid]):
            self._loading = True        # 자리가 없어 못 올림 → 원래 상태로
            self.status.setValue(before)
            self._loading = False
        self.store.update(self.uid, status=self.status.value(), category=self.category.value(),
                          importance=self.importance.value(),
                          urgency=self.urgency.value(), start_date=self.start.value(),
                          due_date=self.due.value())
        self._update_badge()
        self.step._style()
        if self.status.value() == ACTIVE and before != ACTIVE and not self.step.edit.text().strip():
            self.step.edit.setFocus()       # 진행 중으로 올렸으면 다음 한 걸음부터
        self.changed.emit(self.uid)

    def _toggle_dev(self, on):
        if self._loading or not self.uid:
            return
        self.flush()
        self.store.update(self.uid, dev=1 if on else 0)
        if on:
            have = {s["key"] for s in self.store.sections(self.uid)}
            missing = [label for key, label, _h in store.DEV_SECTIONS if key not in have]
            if missing and QMessageBox.question(
                    self, "개발 프로젝트",
                    "기획서에 개발할 때 정해 두면 좋은 칸 %d개를 넣을까요?\n\n%s\n\n(필요 없으면 나중에 지워도 돼요)"
                    % (len(missing), "\n".join("· " + m for m in missing))) == QMessageBox.Yes:
                self.store.add_dev_sections(self.uid)
                self.brief.load(self.uid, keep_scroll=True)
                self._update_progress()
        self.features.set_dev(on)
        self.features.load(self.uid, keep_scroll=True)
        self.tabs.setTabVisible(self.tabs.indexOf(self.devview), on)
        self.devview.refresh()
        if on:
            self.tabs.setCurrentWidget(self.devview)
        self.changed.emit(self.uid)

    def _dev_changed(self, uid):
        """개발 탭에서 바뀜 (개발 시작 → 상태 '진행 중' 등)."""
        row = self.store.get(uid)
        if row is not None and uid == self.uid:
            self._loading = True
            self.status.setValue(row["status"])
            self._loading = False
            self.step._style()
        self.changed.emit(uid)

    def _update_progress(self):
        done, total = self.brief.counts()
        total += 1      # + 한 줄 요약
        done += 1 if self.summary.text().strip() else 0
        self.tabs.setTabText(0, "기획서  %d/%d" % (done, total))

    def _export(self, how):
        if not self.uid:
            return
        self.flush()
        if how == "claude":
            export.send_to_claude(self, self.store, self.uid)
        elif how == "copy":
            QApplication.clipboard().setText(export.idea_markdown(self.store, self.uid))
            QMessageBox.information(self, "복사", "이 아이디어 내용을 마크다운으로 복사했어요.")
        else:
            export.save_idea(self, self.store, self.uid)

    def _section_filled(self, sid, is_new):
        """메모를 기획서 칸에 넣었을 때. 새 칸이면 기획서 탭으로 가서 제목부터 쓰게."""
        if is_new:
            self.brief.load(self.uid, focus=sid, keep_scroll=True)
            self.tabs.setCurrentWidget(self.brief)
        else:
            self.brief.reload()

    def _update_badge(self):
        q = quadrant(self.importance.value(), self.urgency.value())
        self.badge.setText(("● " if q else "○ ") + QUADRANTS[q])
        self.badge.setStyleSheet(quad_badge_style(q))
        self.badge.setToolTip("중요도·긴급도가 %d 이상이면 '높음'" % store.HIGH)


# ---------------------------------------------------------------- 메인 창

class PopupScreenFix(QObject):
    """듀얼 모니터에서 창이 엉뚱한 모니터에 뜨는 Qt 버그 보정.
    - 드롭다운 목록: 드롭다운 바로 아래 (파일 정리 앱과 같음)
    - 대화창(새 아이디어·확인 창 등): 본 창 가운데, 본 창과 같은 모니터
    - 메뉴(달력·⋯): 마우스가 있는 모니터 안"""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
            if obj.metaObject().className() == "QComboBoxPrivateContainer":
                combo = obj.parent()
                if isinstance(combo, QComboBox):
                    self.place(obj, combo)
                    QTimer.singleShot(0, lambda: self.place(obj, combo))
            elif isinstance(obj, QDialog) and obj.parentWidget() is not None:
                self.center(obj)
                QTimer.singleShot(0, lambda: self.center(obj))
            elif isinstance(obj, QMenu):
                self.keep_menu(obj)
        return False

    @staticmethod
    def _move_to_screen(win, scr):
        handle = win.windowHandle()
        if handle is not None and handle.screen() is not scr:
            handle.setScreen(scr)

    @classmethod
    def center(cls, dlg):
        if not dlg.isVisible():
            return
        owner = dlg.parentWidget().window()
        og = owner.frameGeometry()
        scr = QApplication.screenAt(og.center()) or owner.screen()
        cls._move_to_screen(dlg, scr)
        avail = scr.availableGeometry()
        fg = dlg.frameGeometry()
        x = og.center().x() - fg.width() // 2
        y = og.center().y() - fg.height() // 2
        x = max(avail.left(), min(x, avail.right() - fg.width() + 1))
        y = max(avail.top(), min(y, avail.bottom() - fg.height() + 1))
        if (x, y) != (fg.x(), fg.y()):
            dlg.move(x, y)

    @classmethod
    def keep_menu(cls, menu):
        scr = QApplication.screenAt(QCursor.pos())
        if scr is None:
            return
        g = menu.geometry()
        if scr.geometry().contains(g.topLeft()):
            return
        cls._move_to_screen(menu, scr)
        avail = scr.availableGeometry()
        p = QCursor.pos()
        menu.move(max(avail.left(), min(p.x(), avail.right() - g.width() + 1)),
                  max(avail.top(), min(p.y(), avail.bottom() - g.height() + 1)))

    @staticmethod
    def place(popup, combo):
        if not popup.isVisible():
            return
        top_left = combo.mapToGlobal(QPoint(0, 0))
        scr = QApplication.screenAt(top_left + QPoint(combo.width() // 2, combo.height() // 2)) or combo.screen()
        handle = popup.windowHandle()
        if handle is not None and handle.screen() is not scr:
            handle.setScreen(scr)
        avail = scr.availableGeometry()
        w, h = max(popup.width(), combo.width()), popup.height()
        if h > avail.height():
            h = avail.height()
            popup.resize(w, h)
        x = min(max(top_left.x(), avail.left()), avail.right() - w + 1)
        y = top_left.y() + combo.height()
        if y + h > avail.bottom() + 1:
            y = top_left.y() - h
        y = max(avail.top(), min(y, avail.bottom() - h + 1))
        popup.move(x, y)


class MainWindow(QMainWindow):
    def __init__(self, data_dir=DATA_DIR):
        super().__init__()
        self.setWindowTitle("아이디어 보드  v%s" % VERSION)
        self.setWindowIcon(QIcon(make_icon()))
        self.data_dir = data_dir
        self.store = store.Store(os.path.join(data_dir, "ideas.db"))
        self.settings_path = os.path.join(data_dir, "settings.json")
        self.settings = self._load_settings()
        self.gantt = None
        self.todo_win = None
        # 폰 동기화 서버: 연결된 폰이 있을 때만 켜 둠 (없으면 '폰 연결' 창을 열 때 켬 → 방화벽 창도 그때만)
        self.sync = sync.SyncServer(os.path.join(data_dir, "sync.json"), self._sync_handle)
        if self.sync.devices():
            self.sync.start()
        self._sync_timer = QTimer(self, interval=200)
        self._sync_timer.timeout.connect(self.sync.poll)
        self._sync_timer.start()

        self.sidebar = Sidebar(self.store)
        self.dashboard = DashboardPage(self.store)
        self.page = IdeaPage(self.store, data_dir)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.page)

        self.split = QSplitter(Qt.Horizontal)
        self.split.addWidget(self.sidebar)
        self.split.addWidget(self.stack)
        self.split.setStretchFactor(1, 1)
        self.split.setChildrenCollapsible(False)
        self.split.setHandleWidth(1)
        self.sidebar.setMinimumWidth(200)
        self.setCentralWidget(self.split)

        self.sidebar.newRequested.connect(self.new_idea)
        self.sidebar.dashboardRequested.connect(self.show_dashboard)
        self.sidebar.ganttRequested.connect(self.open_gantt)
        self.sidebar.todosRequested.connect(self.open_todos)
        self.sidebar.appAction.connect(self._app_action)
        self.sidebar.ideaSelected.connect(self.open_idea)
        self.sidebar.bulkStatus.connect(self.set_status_many)
        self.sidebar.bulkDelete.connect(self.delete_ideas)
        self.page.changed.connect(self._idea_changed)
        self.page.deleteRequested.connect(self.delete_idea)
        self.dashboard.opened.connect(self.open_idea)
        self.dashboard.changed.connect(lambda _u: (self.sidebar.refresh(self.sidebar.current()), self._refresh_gantt()))
        self.dashboard.ganttRequested.connect(self.open_gantt)
        self.dashboard.todosRequested.connect(self.open_todos)
        self.dashboard.todoChanged.connect(self._todos_changed)

        QShortcut(QKeySequence("Ctrl+N"), self, self.new_idea)
        QShortcut(QKeySequence("Ctrl+T"), self, self.open_gantt)
        QShortcut(QKeySequence("Ctrl+Shift+T"), self, self.open_todos)
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: (self.sidebar.search.setFocus(),
                                                         self.sidebar.search.selectAll()))

        geo = self.settings.get("geometry")
        # 저장된 자리가 지금 없는 모니터면 (모니터를 뺐을 때) 기본 자리로
        if geo and QApplication.screenAt(QRect(*geo).center()) is not None:
            self.setGeometry(*geo)
        else:
            self.resize(1200, 760)
        if self.settings.get("maximized"):
            self.setWindowState(Qt.WindowMaximized)
        self.split.setSizes([self.settings.get("sidebar_width", 270), 900])

        self.sidebar.set_view_state(self.settings.get("list_view", {}))
        self.sidebar.viewChanged.connect(self._save_settings)
        self.sidebar.refresh()
        self.sidebar.set_todo_count(self.store.open_todo_count())
        self.show_dashboard()

    # ---------- 화면 전환 ----------
    def show_dashboard(self):
        self.page.flush()
        self.page.uid = None
        self.sidebar.select(None)
        self.dashboard.refresh()
        self.stack.setCurrentWidget(self.dashboard)

    def open_idea(self, uid):
        if self.page.load(uid):
            self.sidebar.select(uid)
            self.stack.setCurrentWidget(self.page)
        else:
            self.show_dashboard()

    # ---------- 동작 ----------
    def new_idea(self):
        dlg = NewIdeaDialog(self.store.categories(), self)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        if v["status"] == ACTIVE and not focus.ensure_room(self, self.store, new=1):
            v["status"] = STATUSES[0]
            QMessageBox.information(self, "새로운 아이디어", "진행 중 자리가 없어서 '%s'에 넣었어요." % STATUSES[0])
        uid = self.store.create(v.pop("title"), **v)
        if v.get("dev"):
            self.store.add_dev_sections(uid)
        self.sidebar.search.clear()
        self.sidebar.refresh(uid)
        self.open_idea(uid)
        self._refresh_gantt()

    def delete_idea(self, uid):
        self.delete_ideas([uid])

    def delete_ideas(self, uids):
        self.page.flush()
        rows = [r for r in (self.store.get(u) for u in uids) if r is not None]
        if not rows:
            return
        if len(rows) == 1:
            msg = "'%s' 아이디어를 삭제할까요?" % (rows[0]["title"] or "(제목 없음)")
        else:
            names = "\n".join("· " + (r["title"] or "(제목 없음)") for r in rows[:8])
            more = "\n… 외 %d개" % (len(rows) - 8) if len(rows) > 8 else ""
            msg = "아이디어 %d개를 삭제할까요?\n\n%s%s\n" % (len(rows), names, more)
        if QMessageBox.question(self, "삭제", msg + "\n기획서와 메모도 함께 사라져요.") != QMessageBox.Yes:
            return
        gone = {r["uuid"] for r in rows}
        if self.page.uid in gone:
            self.page.uid = None
        self.store.delete_many(sorted(gone))
        self.sidebar.end_pick()
        if self.stack.currentWidget() is self.page and self.page.uid is None:
            self.show_dashboard()
        self._after_remote_change(gone)

    def set_status_many(self, uids, status):
        self.page.flush()
        if status == ACTIVE and not focus.ensure_room(self, self.store, uids):
            self._after_remote_change(set())        # 정리 창에서 다른 걸 내렸을 수 있음
            return
        self.store.set_status_many(uids, status)
        self.sidebar.end_pick()
        self._after_remote_change(set(uids))

    def _idea_changed(self, uid):
        self.sidebar.refresh(uid)
        self.sidebar.select(uid)
        self._refresh_gantt()

    def _app_action(self, what):
        self.page.flush()
        if what == "export_all":
            export.export_all(self, self.store)
        elif what == "backup":
            export.backup(self, self.store)
        elif what == "import":
            self.import_data()
        elif what == "phone":
            self.open_phone()
        elif what == "data_dir":
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.data_dir))

    # ---------- 폰 동기화 ----------
    def open_phone(self):
        if not self.sync.running:
            self.sync.start()
        PhoneDialog(self.sync, self).exec()

    def _sync_handle(self, req):
        """폰이 보낸 변경을 합치고, 지난번 뒤로 PC에서 바뀐 것을 돌려줌 (메인 스레드에서 실행)."""
        self.page.flush()
        n, touched = self.store.apply_changes(req.get("changes") or {})
        out = self.store.changes_since(int(req.get("since") or 0))
        server_time = store.now_ms()
        if n:
            self._after_remote_change(touched)
        return {"ok": True, "changes": out, "server_time": server_time, "applied": n}

    def _after_remote_change(self, touched):
        self.sidebar.refresh(self.sidebar.current())
        if self.stack.currentWidget() is self.page and self.page.uid in touched:
            self.open_idea(self.page.uid)       # 지워졌으면 대시보드로
        elif self.stack.currentWidget() is self.dashboard:
            self.dashboard.refresh()
        self._refresh_gantt()
        self._todos_changed()

    def import_data(self):
        """다른 ideas.db(예전 폴더·백업·다른 PC)를 지금 데이터에 합친다."""
        path, _ = QFileDialog.getOpenFileName(self, "예전 데이터·백업 가져오기", self.data_dir,
                                              "아이디어 보드 데이터 (*.db)")
        if not path:
            return
        cur = os.path.join(self.data_dir, "ideas.db")
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(cur)):
            QMessageBox.information(self, "가져오기", "지금 쓰고 있는 파일이에요.")
            return
        bk = datadir.backup_now(self.data_dir, "합치기전")
        try:
            added, changed = self.store.merge_from(path)
        except Exception as e:      # 깨진 파일·다른 프로그램 파일
            QMessageBox.warning(self, "가져오기", "가져오지 못했어요.\n%s" % e)
            return
        uid = self.page.uid if self.stack.currentWidget() is self.page else None
        self.sidebar.refresh(uid)
        if uid:
            self.open_idea(uid)
        else:
            self.show_dashboard()
        self._refresh_gantt()
        QMessageBox.information(self, "가져오기", "합쳤어요. (아이디어 %d개)\n새로 들어온 항목 %d개 · 더 최근 것으로 바뀐 항목 %d개\n"
                                "(항목 = 아이디어·기획서 칸·메모·기능·링크)\n\n합치기 전 데이터는 백업해 뒀어요:\n%s"
                                % (self.store.idea_count(), added, changed, bk or "-"))

    # ---------- 할일 ----------
    def open_todos(self):
        if self.todo_win is None:
            self.todo_win = TodoWindow(self.store)          # 부모 없음 = 본 창과 따로 최소화·이동
            self.todo_win.setWindowIcon(self.windowIcon())
            self.todo_win.apply_prefs(self.settings.get("todo_view", {}))
            self.todo_win.changed.connect(self._todos_changed_from_window)
            self.todo_win.openIdea.connect(self._open_from_gantt)
            geo = self.settings.get("todo_geometry")
            if geo and QApplication.screenAt(QRect(*geo).center()) is not None:
                self.todo_win.setGeometry(*geo)
            self.todo_win.finished.connect(self._save_settings)
        self.todo_win.show()
        self.todo_win.raise_()
        self.todo_win.activateWindow()

    def _todos_changed(self):
        """대시보드 칸에서 체크했을 때."""
        self.sidebar.set_todo_count(self.store.open_todo_count())
        if self.todo_win is not None and self.todo_win.isVisible():
            self.todo_win.refresh()

    def _todos_changed_from_window(self):
        self.sidebar.set_todo_count(self.store.open_todo_count())
        if self.stack.currentWidget() is self.dashboard:
            self.dashboard.todos.fill(self.store.todos())

    def open_gantt(self):
        if self.gantt is None:
            self.gantt = GanttWindow(self.store)            # 부모 없음 = 본 창과 따로 최소화·이동
            self.gantt.setWindowIcon(self.windowIcon())
            self.gantt.opened.connect(self._open_from_gantt)
            self.gantt.changed.connect(self._gantt_dates_changed)
            geo = self.settings.get("gantt_geometry")
            if geo and QApplication.screenAt(QRect(*geo).center()) is not None:
                self.gantt.setGeometry(*geo)
            self.gantt.finished.connect(self._save_settings)
        self.gantt.show()
        self.gantt.raise_()
        self.gantt.activateWindow()

    def _gantt_dates_changed(self, uid):
        """일정표에서 막대를 끌어 날짜가 바뀜 → 목록·열린 화면에도 반영."""
        self.sidebar.refresh(self.sidebar.current())
        if self.stack.currentWidget() is self.page and self.page.uid == uid:
            self.page.load(uid)
        elif self.stack.currentWidget() is self.dashboard:
            self.dashboard.refresh()

    def _open_from_gantt(self, uid):
        self.open_idea(uid)
        self.raise_()
        self.activateWindow()

    def _refresh_gantt(self):
        if self.gantt is not None and self.gantt.isVisible():
            self.gantt.refresh()

    # ---------- 설정 ----------
    def _load_settings(self):
        try:
            with open(self.settings_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def closeEvent(self, ev):
        self.page.flush()
        self.sync.stop()
        self._save_settings()
        for win in (self.gantt, self.todo_win):      # 따로 떠 있는 창도 같이 닫기
            if win is not None:
                win.close()
        super().closeEvent(ev)

    def _save_settings(self):
        g = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.settings["geometry"] = [g.x(), g.y(), g.width(), g.height()]
        self.settings["maximized"] = self.isMaximized()
        self.settings["sidebar_width"] = self.split.sizes()[0]
        self.settings["list_view"] = self.sidebar.view_state()
        if self.todo_win is not None:
            self.settings["todo_view"] = self.todo_win.view_prefs()
        for key, win in (("gantt_geometry", self.gantt), ("todo_geometry", self.todo_win)):
            if win is not None:
                gg = win.normalGeometry() if win.isMaximized() else win.geometry()
                self.settings[key] = [gg.x(), gg.y(), gg.width(), gg.height()]
        try:
            os.makedirs(self.data_dir, exist_ok=True)
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=1)
        except OSError:
            pass


def main():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("dev.ideaboard")
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setFont(QFont("Malgun Gothic", 10))
    theme.apply(app)
    app._popup_fix = PopupScreenFix(app)
    app.installEventFilter(app._popup_fix)
    QLocale.setDefault(QLocale(QLocale.Korean, QLocale.SouthKorea))
    tr = QTranslator(app)       # 예/아니요 같은 기본 버튼을 한국어로
    tr_dir = (QLibraryInfo.path(QLibraryInfo.TranslationsPath) if hasattr(QLibraryInfo, "path")
              else QLibraryInfo.location(QLibraryInfo.TranslationsPath))
    if tr.load("qtbase_ko", tr_dir):
        app.installTranslator(tr)
    notes = datadir.prepare(DATA_DIR, LEGACY_DATA_DIR, VERSION)
    w = MainWindow()
    w.show()
    if w.store.newer_file:
        notes.append("이 기록은 더 새 버전의 아이디어 보드에서 만든 거예요.\n"
                     "이 버전에서는 일부 내용이 안 보일 수 있으니 새 버전을 쓰는 게 좋아요.")
    if notes:
        QTimer.singleShot(400, lambda: QMessageBox.information(w, "아이디어 보드", "\n\n".join(notes)))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

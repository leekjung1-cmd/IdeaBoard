"""다크 그레이 테마: 색은 전부 여기서."""
import ctypes

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QStyleFactory

WINDOW = "#252526"      # 창 바탕
BASE = "#1e1e1e"        # 목록 바탕
ALT = "#2a2a2b"
PANEL = "#2d2d30"       # 버튼·헤더
BORDER = "#3c3c3c"
TEXT = "#e4e4e4"
TEXT_DIM = "#8f8f8f"    # 설명 글씨
TEXT_OFF = "#5f5f5f"    # 꺼진 버튼·없는 폴더
ACCENT = "#3b8eea"      # 체크·테두리
HIGHLIGHT = "#264f78"   # 목록 선택

SEL_BG = QColor("#1f3f63")        # 바구니에 담긴 항목
SEL_HOVER_BG = QColor("#28507c")
HOVER_BG = QColor("#2f3338")      # 마우스 올림
FOCUS = QColor("#6a8fb8")
CHECK_BOX_BG = QColor(40, 40, 40, 230)
CHECK_BOX_EDGE = QColor("#9a9a9a")
DANGER = "#ff6b6b"
GOOD = "#6fb3ff"
STAR = "#f2c14e"
SIDEBAR = "#1d1d1e"      # 왼쪽 목록 바탕
ITEM_HOVER = "#2c2d30"
ITEM_SEL = "#33363b"

# 사분면 색 (store.QUADRANTS 번호와 같음)
QUAD = {1: "#e5534b", 2: "#3b8eea", 3: "#d29922", 4: "#8b949e", 0: "#5a5a5a"}

STYLE = f"""
QWidget {{ color:{TEXT}; }}
QToolTip {{ color:{TEXT}; background:{PANEL}; border:1px solid {BORDER}; padding:4px; }}
QLineEdit, QComboBox, QSpinBox {{
    background:{BASE}; border:1px solid {BORDER}; border-radius:4px; padding:3px 6px;
    selection-background-color:{HIGHLIGHT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color:{ACCENT}; }}
QComboBox QAbstractItemView {{ background:{PANEL}; border:1px solid {BORDER}; selection-background-color:{HIGHLIGHT}; }}
QPushButton {{
    background:{PANEL}; border:1px solid {BORDER}; border-radius:5px; padding:5px 12px;
}}
QPushButton:hover {{ background:#383a3e; border-color:#4a4a4a; }}
QPushButton:pressed {{ background:#1f1f1f; }}
QPushButton:disabled {{ color:{TEXT_OFF}; background:#2a2a2a; border-color:#333; }}
QToolButton {{ border-radius:4px; padding:3px; }}
QToolButton:hover {{ background:#383a3e; }}
QTreeView, QListView, QTableWidget, QListWidget {{
    background:{BASE}; alternate-background-color:{ALT}; border:1px solid {BORDER};
}}
QHeaderView::section {{
    background:{PANEL}; color:#cfcfcf; border:none; border-right:1px solid {BORDER};
    border-bottom:1px solid {BORDER}; padding:4px 6px;
}}
QSplitter::handle {{ background:{WINDOW}; }}
QStatusBar {{ background:#1b1b1c; color:#bdbdbd; }}
QStatusBar QLabel {{ color:#bdbdbd; }}
QProgressBar {{ background:{BASE}; border:1px solid {BORDER}; border-radius:4px; text-align:center; }}
QProgressBar::chunk {{ background:{ACCENT}; border-radius:3px; }}
QMenu {{ background:{PANEL}; border:1px solid {BORDER}; padding:4px; }}
QMenu::item {{ padding:5px 22px 5px 14px; border-radius:4px; }}
QMenu::item:selected {{ background:{HIGHLIGHT}; }}
QMenu::separator {{ height:1px; background:{BORDER}; margin:4px 6px; }}
QScrollBar:vertical {{ background:{BASE}; width:12px; margin:0; }}
QScrollBar:horizontal {{ background:{BASE}; height:12px; margin:0; }}
QScrollBar::handle {{ background:#4a4a4d; border-radius:5px; margin:2px; min-height:24px; min-width:24px; }}
QScrollBar::handle:hover {{ background:#5c5c60; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:none; }}
QMessageBox, QDialog {{ background:{WINDOW}; }}
QTextEdit, QPlainTextEdit {{
    background:{BASE}; border:1px solid {BORDER}; border-radius:4px; padding:4px;
    selection-background-color:{HIGHLIGHT};
}}
QTextEdit:focus, QPlainTextEdit:focus {{ border-color:{ACCENT}; }}
QTabWidget::pane {{ border:none; border-top:1px solid {BORDER}; }}
QTabBar::tab {{
    background:transparent; color:{TEXT_DIM}; padding:7px 16px; border:none;
    border-bottom:2px solid transparent;
}}
QTabBar::tab:selected {{ color:{TEXT}; border-bottom-color:{ACCENT}; }}
QTabBar::tab:hover {{ color:{TEXT}; }}
QCalendarWidget QWidget {{ alternate-background-color:{PANEL}; }}
QCalendarWidget QAbstractItemView {{ background:{BASE}; selection-background-color:{HIGHLIGHT}; }}
QCalendarWidget QToolButton {{ color:{TEXT}; padding:4px 8px; }}
#qt_calendar_navigationbar {{ background:{PANEL}; }}
QCheckBox::indicator {{ width:14px; height:14px; border:1px solid #8a8a8a; border-radius:3px; background:{BASE}; }}
QCheckBox::indicator:hover {{ border-color:{ACCENT}; }}
QCheckBox::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; }}
"""


def _palette():
    p = QPalette()
    c = QColor
    p.setColor(QPalette.Window, c(WINDOW))
    p.setColor(QPalette.WindowText, c(TEXT))
    p.setColor(QPalette.Base, c(BASE))
    p.setColor(QPalette.AlternateBase, c(ALT))
    p.setColor(QPalette.ToolTipBase, c(PANEL))
    p.setColor(QPalette.ToolTipText, c(TEXT))
    p.setColor(QPalette.PlaceholderText, c(TEXT_DIM))
    p.setColor(QPalette.Text, c(TEXT))
    p.setColor(QPalette.Button, c(PANEL))
    p.setColor(QPalette.ButtonText, c(TEXT))
    p.setColor(QPalette.BrightText, c(DANGER))
    p.setColor(QPalette.Light, c("#3a3a3a"))
    p.setColor(QPalette.Midlight, c("#333333"))
    p.setColor(QPalette.Mid, c("#2a2a2a"))
    p.setColor(QPalette.Dark, c("#1a1a1a"))
    p.setColor(QPalette.Shadow, c("#000000"))
    p.setColor(QPalette.Highlight, c(HIGHLIGHT))
    p.setColor(QPalette.HighlightedText, c("#ffffff"))
    p.setColor(QPalette.Link, c(GOOD))
    for role, col in ((QPalette.Text, TEXT_OFF), (QPalette.WindowText, TEXT_OFF),
                      (QPalette.ButtonText, TEXT_OFF)):
        p.setColor(QPalette.Disabled, role, c(col))
    return p


class _DarkTitleBars(QObject):
    """새 창(대화상자 포함)이 뜰 때 윈도우 제목 표시줄도 어둡게."""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Show and getattr(obj, "isWindow", None) and obj.isWindow():
            if not obj.property("_dark_title"):
                obj.setProperty("_dark_title", True)
                try:
                    hwnd = int(obj.winId())
                    val = ctypes.c_int(1)
                    for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (신/구 윈도우)
                        if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                                hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                            break
                except Exception:
                    pass
        return False


def apply(app):
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setPalette(_palette())
    app.setStyleSheet(STYLE)
    app._dark_titles = _DarkTitleBars(app)
    app.installEventFilter(app._dark_titles)

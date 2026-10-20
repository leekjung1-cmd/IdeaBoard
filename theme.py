"""색·모서리·글꼴은 전부 여기서. 두 가지 모양:

- dark  = '차분한 작업실': 따뜻한 먹색 바탕 + 세이지 초록 한 색
- light = '미니멀 그리드': 흰 바탕 + 굵은 글자 + 각진 선 + 주황 신호색

설정(settings.json 의 "theme": auto / dark / light)을 따르고, auto 면 윈도우의 앱 모드(다크/라이트)를 따름.
바꾸면 프로그램을 다시 켜야 적용됨 (모든 화면이 켤 때 색을 읽어 감).
"""
import ctypes
import json
import os
import re
import sys

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QStyleFactory, QWidget

DARK = dict(
    WINDOW="#1c1b19", BASE="#161513", ALT="#201f1c", PANEL="#24231f", BORDER="#33312d", LINE="#2a2925",
    TEXT="#e8e4dc", TEXT_DIM="#9a958b", TEXT_OFF="#6f6b62",
    ACCENT="#9db58a", ON_ACCENT="#1c1b19", HIGHLIGHT="#3a4433",
    SIDEBAR="#161513", ITEM_HOVER="#22211e", ITEM_SEL="#2b2a25", CHIP="#24231f", BUTTON_HOVER="#2e2c28",
    DANGER="#e07a5f", GOOD="#9db58a", STAR="#d4a85a", STRONG="#33312d",
    QUAD={1: "#d9735b", 2: "#86a9c4", 3: "#d4a85a", 4: "#8a867d", 0: "#5a5750"},
    RADIUS=8, SQUARE=False, DARK=True,
)
LIGHT = dict(
    WINDOW="#ffffff", BASE="#ffffff", ALT="#f6f6f6", PANEL="#f5f5f5", BORDER="#e2e2e2", LINE="#ececec",
    TEXT="#111111", TEXT_DIM="#666666", TEXT_OFF="#a3a3a3",
    ACCENT="#ff4f12", ON_ACCENT="#ffffff", HIGHLIGHT="#ffe3d8",
    SIDEBAR="#ffffff", ITEM_HOVER="#f4f4f4", ITEM_SEL="#fff1eb", CHIP="#ffffff", BUTTON_HOVER="#ececec",
    DANGER="#d92d20", GOOD="#1f7a3a", STAR="#d99a00", STRONG="#111111",
    QUAD={1: "#ff4f12", 2: "#2563eb", 3: "#d99a00", 4: "#9a9a9a", 0: "#c8c8c8"},
    RADIUS=2, SQUARE=True, DARK=False,
)


def _settings_theme():
    path = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "IdeaBoard", "settings.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("theme", "auto")
    except (OSError, ValueError):
        return "auto"


def windows_dark():
    """윈도우 설정 > 개인 설정 > 색 > 앱 모드가 '어둡게'인지."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return True


MODE = _settings_theme()
if os.environ.get("IDEABOARD_THEME") in ("dark", "light"):      # 테스트용
    MODE = os.environ["IDEABOARD_THEME"]
_P = DARK if MODE == "dark" or (MODE != "light" and windows_dark()) else LIGHT
globals().update({k: v for k, v in _P.items()})

R = RADIUS                       # 카드·칸 모서리
R_SM = max(0, RADIUS - 3)        # 버튼·입력칸 모서리
SEL_BG = QColor(HIGHLIGHT)
SEL_HOVER_BG = QColor(HIGHLIGHT)
HOVER_BG = QColor(ITEM_HOVER)
FOCUS = QColor(ACCENT)
CHECK_BOX_BG = QColor(BASE)
CHECK_BOX_EDGE = QColor(TEXT_DIM)


def r(n):
    """원래 모서리 n → 지금 모양에 맞는 모서리 (미니멀 그리드면 거의 각지게)."""
    return min(n, 2) if SQUARE else n


def pill(h):
    """알약 모양(높이 h) 모서리."""
    return 2 if SQUARE else h / 2


# 화면마다 따로 쓴 스타일시트의 모서리도 맞춤 (border-radius:Npx → 미니멀이면 2px 이하)
_RADIUS_RE = re.compile(r"border-radius\s*:\s*(\d+)px")
_orig_set_style = QWidget.setStyleSheet


def _set_style(self, css):
    if SQUARE and css:
        css = _RADIUS_RE.sub(lambda m: "border-radius:%dpx" % min(int(m.group(1)), 2), css)
    _orig_set_style(self, css)


QWidget.setStyleSheet = _set_style

FONT_FAMILY = "Malgun Gothic"


def load_font():
    """Noto Sans KR (무료 글꼴, 같이 들어 있음). 없으면 맑은 고딕."""
    global FONT_FAMILY
    if "Noto Sans KR" in QFontDatabase.families():
        FONT_FAMILY = "Noto Sans KR"
        return FONT_FAMILY
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "fonts", "NotoSansKR-VF.ttf")
    if os.path.exists(path):
        fid = QFontDatabase.addApplicationFont(path)
        fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if fams:
            FONT_FAMILY = fams[0]
    return FONT_FAMILY


def font(size=10, weight=QFont.Normal):
    f = QFont(FONT_FAMILY, size)
    f.setWeight(weight)
    return f


STYLE = f"""
QWidget {{ color:{TEXT}; }}
QToolTip {{ color:{TEXT}; background:{PANEL}; border:1px solid {BORDER}; padding:5px 7px; }}
QLineEdit, QComboBox, QSpinBox {{
    background:{BASE}; border:1px solid {BORDER}; border-radius:{R_SM}px; padding:4px 7px;
    selection-background-color:{HIGHLIGHT}; selection-color:{TEXT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color:{ACCENT}; }}
QComboBox QAbstractItemView {{ background:{PANEL}; border:1px solid {BORDER}; selection-background-color:{HIGHLIGHT}; selection-color:{TEXT}; }}
QPushButton {{
    background:{PANEL}; border:1px solid {BORDER}; border-radius:{R_SM}px; padding:5px 13px;
}}
QPushButton:hover {{ background:{BUTTON_HOVER}; border-color:{TEXT_OFF}; }}
QPushButton:pressed {{ background:{ITEM_SEL}; }}
QPushButton:disabled {{ color:{TEXT_OFF}; background:{ALT}; border-color:{BORDER}; }}
QPushButton:default {{ background:{ACCENT}; color:{ON_ACCENT}; border-color:{ACCENT}; }}
QToolButton {{ border-radius:{R_SM}px; padding:3px; }}
QToolButton:hover {{ background:{BUTTON_HOVER}; }}
QTreeView, QListView, QTableWidget, QListWidget {{
    background:{BASE}; alternate-background-color:{ALT}; border:1px solid {BORDER};
    selection-background-color:{HIGHLIGHT}; selection-color:{TEXT};
}}
QHeaderView::section {{
    background:{PANEL}; color:{TEXT_DIM}; border:none; border-right:1px solid {BORDER};
    border-bottom:1px solid {BORDER}; padding:4px 6px;
}}
QSplitter::handle {{ background:{STRONG if SQUARE else BORDER}; }}
QStatusBar {{ background:{SIDEBAR}; color:{TEXT_DIM}; }}
QProgressBar {{ background:{LINE}; border:none; border-radius:{R_SM}px; text-align:center; }}
QProgressBar::chunk {{ background:{ACCENT}; border-radius:{R_SM}px; }}
QMenu {{ background:{PANEL if not SQUARE else BASE}; border:1px solid {BORDER if not SQUARE else STRONG}; padding:4px; }}
QMenu::item {{ padding:6px 22px 6px 14px; border-radius:{R_SM}px; }}
QMenu::item:selected {{ background:{ITEM_SEL}; color:{TEXT}; }}
QMenu::item:disabled {{ color:{TEXT_OFF}; }}
QMenu::separator {{ height:1px; background:{BORDER}; margin:4px 6px; }}
QScrollBar:vertical {{ background:transparent; width:10px; margin:0; }}
QScrollBar:horizontal {{ background:transparent; height:10px; margin:0; }}
QScrollBar::handle {{ background:{BORDER}; border-radius:{R_SM + 2 if not SQUARE else 0}px; margin:2px; min-height:24px; min-width:24px; }}
QScrollBar::handle:hover {{ background:{TEXT_OFF}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:none; }}
QMessageBox, QDialog {{ background:{WINDOW}; }}
QTextEdit, QPlainTextEdit {{
    background:{BASE}; border:1px solid {BORDER}; border-radius:{R_SM}px; padding:5px;
    selection-background-color:{HIGHLIGHT}; selection-color:{TEXT};
}}
QTextEdit:focus, QPlainTextEdit:focus {{ border-color:{ACCENT}; }}
QTabWidget::pane {{ border:none; border-top:1px solid {BORDER}; }}
QTabBar::tab {{
    background:transparent; color:{TEXT_DIM}; padding:8px 16px; border:none;
    border-bottom:2px solid transparent;
}}
QTabBar::tab:selected {{ color:{TEXT}; border-bottom-color:{ACCENT if not SQUARE else STRONG}; font-weight:{'bold' if SQUARE else 'normal'}; }}
QTabBar::tab:hover {{ color:{TEXT}; }}
QCalendarWidget QWidget {{ alternate-background-color:{PANEL}; }}
QCalendarWidget QAbstractItemView {{ background:{BASE}; selection-background-color:{ACCENT}; selection-color:{ON_ACCENT}; }}
QCalendarWidget QToolButton {{ color:{TEXT}; padding:4px 8px; }}
#qt_calendar_navigationbar {{ background:{PANEL}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width:14px; height:14px; border:1px solid {TEXT_DIM}; background:{BASE}; }}
QCheckBox::indicator {{ border-radius:{R_SM}px; }}
QRadioButton::indicator {{ border-radius:7px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color:{ACCENT}; }}
QCheckBox::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; }}
QRadioButton::indicator:checked {{ background:{ACCENT}; border:3px solid {BASE}; outline:1px solid {ACCENT}; }}
QSlider::groove:horizontal {{ height:3px; background:{BORDER}; }}
QSlider::handle:horizontal {{ width:12px; margin:-5px 0; border-radius:{6 if not SQUARE else 0}px; background:{ACCENT}; }}
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
    p.setColor(QPalette.PlaceholderText, c(TEXT_OFF))
    p.setColor(QPalette.Text, c(TEXT))
    p.setColor(QPalette.Button, c(PANEL))
    p.setColor(QPalette.ButtonText, c(TEXT))
    p.setColor(QPalette.BrightText, c(DANGER))
    p.setColor(QPalette.Light, c(BORDER))
    p.setColor(QPalette.Midlight, c(LINE))
    p.setColor(QPalette.Mid, c(ALT))
    p.setColor(QPalette.Dark, c(SIDEBAR))
    p.setColor(QPalette.Shadow, c("#000000"))
    p.setColor(QPalette.Highlight, c(ACCENT))
    p.setColor(QPalette.HighlightedText, c(ON_ACCENT))
    p.setColor(QPalette.Link, c(ACCENT))
    for role, col in ((QPalette.Text, TEXT_OFF), (QPalette.WindowText, TEXT_OFF),
                      (QPalette.ButtonText, TEXT_OFF)):
        p.setColor(QPalette.Disabled, role, c(col))
    return p


class _TitleBars(QObject):
    """새 창(대화상자 포함)이 뜰 때 윈도우 제목 표시줄도 테마에 맞춤 (다크면 어둡게)."""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Show and getattr(obj, "isWindow", None) and obj.isWindow():
            if not obj.property("_title_done"):
                obj.setProperty("_title_done", True)
                try:
                    hwnd = int(obj.winId())
                    val = ctypes.c_int(1 if DARK else 0)
                    for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (신/구 윈도우)
                        if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                                hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                            break
                except Exception:
                    pass
        return False


def apply(app):
    app.setStyle(QStyleFactory.create("Fusion"))
    load_font()
    app.setFont(font(10))
    app.setPalette(_palette())
    app.setStyleSheet(STYLE)
    app._title_bars = _TitleBars(app)
    app.installEventFilter(app._title_bars)

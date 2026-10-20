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
    RADIUS=10, SQUARE=False, MINIMAL=False, DARK=True, FIELD="#161513", BUTTON="#26251f",
)
LIGHT = dict(
    WINDOW="#ffffff", BASE="#ffffff", ALT="#fafafa", PANEL="#f7f7f7", BORDER="#e6e6e6", LINE="#efefef",
    TEXT="#111111", TEXT_DIM="#6b6b6b", TEXT_OFF="#a8a8a8",
    ACCENT="#ff4f12", ON_ACCENT="#ffffff", HIGHLIGHT="#ffe3d8",
    SIDEBAR="#fbfbfb", ITEM_HOVER="#f3f3f3", ITEM_SEL="#fff1eb", CHIP="#ffffff", BUTTON_HOVER="#f3f3f3",
    DANGER="#d92d20", GOOD="#1f7a3a", STAR="#d99a00", STRONG="#111111",
    QUAD={1: "#ff4f12", 2: "#2563eb", 3: "#d99a00", 4: "#9a9a9a", 0: "#c8c8c8"},
    RADIUS=10, SQUARE=False, MINIMAL=True, DARK=False, FIELD="#ffffff", BUTTON="#ffffff",
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
R_SM = 7                         # 버튼·입력칸 모서리
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

def _asset_dir():
    import tempfile
    d = os.path.join(tempfile.gettempdir(), "ideaboard-ui", "dark" if DARK else "light")
    os.makedirs(d, exist_ok=True)
    files = {
        "chevron.svg": ('M6 9l6 6 6-6', TEXT_DIM, 2),
        "chevron-up.svg": ('M6 15l6-6 6 6', TEXT_DIM, 2),
        "check.svg": ('M5 12.5l4.5 4.5L19 7', ON_ACCENT, 3),
    }
    out = {}
    for name, (d_, color, w) in files.items():
        path = os.path.join(d, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%s" '
                    'stroke-width="%s" stroke-linecap="round" stroke-linejoin="round"><path d="%s"/></svg>' % (color, w, d_))
        out[name] = path.replace("\\", "/")
    dot = os.path.join(d, "dot.svg")
    with open(dot, "w", encoding="utf-8") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5" fill="%s"/></svg>' % ON_ACCENT)
    out["dot.svg"] = dot.replace("\\", "/")
    return out


try:
    _A = _asset_dir()
except OSError:
    _A = {}


def _url(name):
    return "url(%s)" % _A[name] if name in _A else "none"


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
QToolTip {{ color:{TEXT}; background:{PANEL}; border:1px solid {BORDER}; border-radius:6px; padding:6px 8px; }}

QLineEdit, QComboBox, QSpinBox, QDateEdit {{
    background:{FIELD}; border:1px solid {BORDER}; border-radius:{R_SM}px; padding:5px 10px; min-height:20px;
    selection-background-color:{HIGHLIGHT}; selection-color:{TEXT};
}}
QLineEdit:hover, QComboBox:hover {{ border-color:{TEXT_OFF}; }}
QLineEdit:focus, QComboBox:focus, QComboBox:on {{ border-color:{ACCENT}; }}
QComboBox {{ padding-right:28px; combobox-popup:0; }}
QComboBox::drop-down {{ subcontrol-origin:padding; subcontrol-position:center right; width:28px; border:none; background:transparent; }}
QComboBox::down-arrow {{ image:{_url("chevron.svg")}; width:12px; height:12px; }}
QComboBox::down-arrow:on {{ image:{_url("chevron-up.svg")}; }}
QComboBox QAbstractItemView {{
    background:{PANEL if DARK else BASE}; border:1px solid {BORDER}; border-radius:8px; padding:4px; outline:0;
    selection-background-color:{ITEM_SEL}; selection-color:{TEXT};
}}
QComboBox QAbstractItemView::item {{ min-height:28px; padding:0 8px; border-radius:6px; }}
QComboBox QAbstractItemView::item:hover {{ background:{ITEM_HOVER}; }}

QPushButton {{
    background:{BUTTON}; border:1px solid {BORDER}; border-radius:{R_SM}px; padding:6px 14px; min-height:20px;
}}
QPushButton:hover {{ background:{BUTTON_HOVER}; border-color:{TEXT_OFF}; }}
QPushButton:pressed {{ background:{ITEM_SEL}; }}
QPushButton:disabled {{ color:{TEXT_OFF}; background:{ALT}; border-color:{LINE}; }}
QPushButton:default {{ background:{ACCENT}; color:{ON_ACCENT}; border-color:{ACCENT}; font-weight:bold; }}
QPushButton:default:hover {{ background:{ACCENT}; border-color:{TEXT if not DARK else ACCENT}; }}
QPushButton#seg {{ border-radius:15px; padding:4px 16px; min-height:18px; }}
QPushButton#seg:checked {{ background:{ACCENT}; color:{ON_ACCENT}; border-color:{ACCENT}; font-weight:bold; }}
QPushButton#dateField {{ background:{FIELD}; text-align:left; padding:5px 10px; font-weight:normal; }}
QPushButton#dateField:hover {{ border-color:{TEXT_OFF}; background:{FIELD}; }}
QToolButton {{ border:none; border-radius:{R_SM}px; padding:4px; background:transparent; }}
QToolButton:hover {{ background:{BUTTON_HOVER}; }}
QToolButton::menu-indicator {{ image:none; width:0; }}

QTreeView, QListView, QTableWidget, QListWidget {{
    background:{BASE}; alternate-background-color:{ALT}; border:1px solid {BORDER}; border-radius:8px;
    selection-background-color:{ITEM_SEL}; selection-color:{TEXT}; outline:0;
}}
QListWidget::item {{ padding:4px 6px; border-radius:6px; }}
QListWidget::item:hover {{ background:{ITEM_HOVER}; }}
QHeaderView::section {{
    background:{PANEL}; color:{TEXT_DIM}; border:none; border-bottom:1px solid {BORDER}; padding:6px 8px;
}}
QSplitter::handle {{ background:{LINE if MINIMAL else BORDER}; }}
QStatusBar {{ background:{SIDEBAR}; color:{TEXT_DIM}; }}
QProgressBar {{ background:{LINE}; border:none; border-radius:3px; max-height:6px; text-align:center; }}
QProgressBar::chunk {{ background:{ACCENT}; border-radius:3px; }}

QMenu {{ background:{PANEL if DARK else BASE}; border:1px solid {BORDER}; border-radius:10px; padding:6px; }}
QMenu::item {{ padding:7px 26px 7px 12px; border-radius:6px; }}
QMenu::item:selected {{ background:{ITEM_SEL}; color:{TEXT}; }}
QMenu::item:disabled {{ color:{TEXT_OFF}; }}
QMenu::separator {{ height:1px; background:{LINE}; margin:5px 8px; }}
QMenu::section {{ color:{TEXT_DIM}; padding:6px 12px 4px 12px; font-weight:bold; }}
QMenu::icon {{ padding-left:8px; }}
QMenu::indicator {{ width:14px; height:14px; left:6px; }}
QMenu::indicator:checked {{ image:{_url("check.svg")}; background:{ACCENT}; border-radius:4px; }}

QScrollBar:vertical {{ background:transparent; width:10px; margin:2px; }}
QScrollBar:horizontal {{ background:transparent; height:10px; margin:2px; }}
QScrollBar::handle {{ background:{BORDER}; border-radius:3px; min-height:28px; min-width:28px; }}
QScrollBar::handle:hover {{ background:{TEXT_OFF}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:none; }}

QMessageBox, QDialog {{ background:{WINDOW}; }}
QDialog QLabel {{ background:transparent; }}
QTextEdit, QPlainTextEdit {{
    background:{FIELD}; border:1px solid {BORDER}; border-radius:{R_SM}px; padding:6px 8px;
    selection-background-color:{HIGHLIGHT}; selection-color:{TEXT};
}}
QTextEdit:focus, QPlainTextEdit:focus {{ border-color:{ACCENT}; }}

QTabWidget::pane {{ border:none; border-top:1px solid {LINE}; }}
QTabBar::tab {{ background:transparent; color:{TEXT_DIM}; padding:9px 16px; border:none; border-bottom:2px solid transparent; }}
QTabBar::tab:selected {{ color:{TEXT}; border-bottom-color:{ACCENT if not MINIMAL else STRONG}; font-weight:bold; }}
QTabBar::tab:hover {{ color:{TEXT}; }}

QCalendarWidget QWidget {{ alternate-background-color:{PANEL}; }}
QCalendarWidget QAbstractItemView {{ background:{BASE}; selection-background-color:{ACCENT}; selection-color:{ON_ACCENT}; border:none; }}
QCalendarWidget QToolButton {{ color:{TEXT}; padding:4px 8px; }}
#qt_calendar_navigationbar {{ background:{PANEL}; }}

QCheckBox, QRadioButton {{ spacing:8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width:15px; height:15px; border:1.5px solid {TEXT_OFF}; background:{FIELD}; }}
QCheckBox::indicator {{ border-radius:5px; }}
QRadioButton::indicator {{ border-radius:8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color:{ACCENT}; }}
QCheckBox::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; image:{_url("check.svg")}; }}
QRadioButton::indicator:checked {{ background:{ACCENT}; border-color:{ACCENT}; image:{_url("dot.svg")}; }}

QSlider::groove:horizontal {{ height:4px; background:{BORDER}; border-radius:2px; }}
QSlider::sub-page:horizontal {{ background:{ACCENT}; border-radius:2px; }}
QSlider::handle:horizontal {{ width:14px; height:14px; margin:-5px 0; border-radius:7px; background:{ACCENT}; }}
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

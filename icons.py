"""선 아이콘 (24칸 격자, 선 굵기 1.8). 이모지 대신 씀. 색은 테마 글자색을 따름.

icon("plus") → QIcon, pixmap("code", 16, color) → QPixmap
"""
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

import theme

# 직접 그린 단순한 도형들 (path d 값)
PATHS = {
    "plus": "M12 5v14M5 12h14",
    "grid": "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
    "gantt": "M4 5h16M4 5v15M7 9h8M10 13h9M7 17h6",
    "check-square": "M4 4h16v16H4zM8 12l3 3 5-6",
    "table": "M3 5h18v15H3zM3 10h18M3 15h18M9 5v15M15 5v15",
    "review": "M6 3h12v18H6zM9 8h6M9 12l2 2 4-4M9 17h6",
    "search": "M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM15.5 15.5L20 20",
    "more": "M5 12h.01M12 12h.01M19 12h.01",
    "code": "M8 7l-5 5 5 5M16 7l5 5-5 5",
    "film": "M3 5h18v14H3zM10 9.5v5l4.5-2.5z",
    "step": "M5 12h12M13 7l5 5-5 5",
    "folder": "M3 6h6l2 2h10v11H3z",
    "chat": "M4 5h16v11H9l-5 4z",
    "cut": "M6 6l12 12M18 6L6 18M4 4h4v4H4zM16 16h4v4h-4z",
    "stairs": "M4 20h5v-5h5v-5h5V5",
    "check": "M5 12.5l4.5 4.5L19 7",
    "pause": "M8 5v14M16 5v14",
    "trash": "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13",
    "bolt": "M13 3L5 14h6l-1 7 8-11h-6z",
    "pin": "M9 4h6l-1 6 3 3H7l3-3zM12 13v8",
    "info": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v6M12 7.5h.01",
    "link": "M10 14l4-4M8.5 11.5l-2 2a3 3 0 0 0 4 4l2-2M15.5 12.5l2-2a3 3 0 0 0-4-4l-2 2",
    "expand": "M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7",
    "play": "M7 4l12 8-12 8z",
    "dot": "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
    "chevron-down": "M6 9l6 6 6-6",
    "warning": "M12 4l9 16H3zM12 10v4M12 17h.01",
    "calendar": "M4 6h16v14H4zM4 10h16M8 3v5M16 3v5",
}


def _svg(name, color, stroke=1.8):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%s" '
            'stroke-width="%s" stroke-linecap="round" stroke-linejoin="round"><path d="%s"/></svg>'
            % (color, stroke, PATHS[name]))


def pixmap(name, size=16, color=None, ratio=2.0):
    color = color or theme.TEXT
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(ratio)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(_svg(name, color).encode())).render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


def icon(name, color=None, size=16):
    """보통 상태 + 꺼진 상태(흐린 색)를 담은 아이콘."""
    ic = QIcon()
    ic.addPixmap(pixmap(name, size, color or theme.TEXT), QIcon.Normal)
    ic.addPixmap(pixmap(name, size, theme.TEXT_OFF), QIcon.Disabled)
    ic.addPixmap(pixmap(name, size, theme.ACCENT), QIcon.Normal, QIcon.On)
    return ic


def draw(p, name, rect, color=None):
    """QPainter 위 rect 자리에 아이콘 그리기."""
    QSvgRenderer(QByteArray(_svg(name, color or theme.TEXT).encode())).render(p, QRectF(rect))

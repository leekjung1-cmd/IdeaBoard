"""듀얼 모니터에서 메뉴·대화창이 엉뚱한 모니터(오른쪽)에 뜨는 Qt 버그 보정 (업무자동화 popupfix.py 와 같음).

왜 생기나: Qt(화면 라이브러리)가 팝업 창을 처음 만들 때 '주 모니터' 소속으로 만들어 버림.
좌표는 맞게 알고 있어도 실제로는 다른 모니터 기준(특히 배율 125%·100% 처럼 다를 때)으로 그려서
엉뚱한 모니터에 뜸. 그래서 좌표가 맞아 보여도 '어느 모니터 소속인지'를 매번 다시 정해 줘야 함.

v0.9.4: Qt 가 말하는 좌표는 맞는데 실제 창은 다른 모니터에 가 있는 경우가 남아 있어서,
마지막에 윈도우에게 직접 '진짜 어디 떠 있나'를 물어보고(실제 픽셀 좌표) 다른 모니터면 그 자리로 옮김.
"""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QDialog, QMenu, QWidget

_u = ctypes.WinDLL("user32", use_last_error=True)


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


_u.MonitorFromPoint.argtypes = (wintypes.POINT, wintypes.DWORD)
_u.MonitorFromPoint.restype = wintypes.HANDLE
_u.MonitorFromRect.argtypes = (ctypes.POINTER(wintypes.RECT), wintypes.DWORD)
_u.MonitorFromRect.restype = wintypes.HANDLE
_u.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_MONITORINFO))
_u.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
_u.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            wintypes.UINT)
_NULL, _NEAREST = 0, 2
_SWP = 0x0001 | 0x0004 | 0x0010            # 크기·쌓임 순서 그대로, 포커스 안 뺏음


def _cursor():
    """실제 픽셀 마우스 위치."""
    p = wintypes.POINT()
    _u.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def _rect(hwnd):
    r = wintypes.RECT()
    _u.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
    return r


def native_keep(win, pt, centered=False):
    """win 이 실제로 pt(실제 픽셀) 와 다른 모니터에 떠 있으면 pt 쪽 모니터로 옮김 (pt 가 왼쪽 위, centered 면 가운데).
    옮겼으면 True."""
    try:
        if not win.isVisible():
            return False
        hwnd = int(win.winId())
        r = _rect(hwnd)
        want = _u.MonitorFromPoint(wintypes.POINT(*pt), _NEAREST)
        now = _u.MonitorFromRect(ctypes.byref(r), _NULL)      # 어느 모니터에도 안 걸쳐 있으면 0
        if now == want:
            return False
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(mi)
        if not _u.GetMonitorInfoW(want, ctypes.byref(mi)):
            return False
        work = mi.rcWork
        w, h = r.right - r.left, r.bottom - r.top
        x, y = (pt[0] - w // 2, pt[1] - h // 2) if centered else pt
        x = max(work.left, min(x, work.right - w))
        y = max(work.top, min(y, work.bottom - h))
        _u.SetWindowPos(wintypes.HWND(hwnd), None, x, y, 0, 0, _SWP)
        return True
    except Exception:
        return False


def _center_of(widget):
    r = _rect(int(widget.window().winId()))
    return (r.left + r.right) // 2, (r.top + r.bottom) // 2


class PopupScreenFix(QObject):
    """- 드롭다운 목록·달력 팝업: 그 칸 바로 아래
    - 대화창: 본 창 가운데, 본 창과 같은 모니터
    - 버튼(⋯ 등)에서 연 메뉴: 그 버튼 바로 아래 / 우클릭 메뉴·트레이 메뉴: 마우스가 있는 모니터 안"""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
            mouse = _cursor()
            if obj.metaObject().className() == "QComboBoxPrivateContainer":
                combo = obj.parent()
                if isinstance(combo, QComboBox):
                    self._later(lambda: self.place(obj, combo), obj, lambda: mouse)
            elif isinstance(obj, QDialog) and obj.parentWidget() is not None:
                self._later(lambda: self.center(obj), obj, lambda: _center_of(obj.parentWidget()), centered=True)
            elif isinstance(obj, QMenu):
                if isinstance(obj.parentWidget(), QMenu):
                    return False                     # 하위 메뉴는 Qt가 상위 메뉴 옆에 붙임
                anchor = self._menu_anchor(obj)
                cursor = QCursor.pos()
                self._later(lambda: self.keep_menu(obj, anchor, cursor), obj, lambda: mouse)
            elif obj.windowType() == Qt.Popup and obj.parentWidget() is not None:   # 날짜 칸 달력 등
                anchor = obj.parentWidget()
                self._later(lambda: self.place(obj, anchor), obj, lambda: mouse)
        return False

    @staticmethod
    def _later(fn, win, where, centered=False):
        """지금 한 번 + Qt가 자리를 다시 잡은 뒤 한 번 더. 매번 마지막에 '진짜 모니터' 확인."""
        def step():
            fn()
            native_keep(win, where(), centered)
        step()
        QTimer.singleShot(0, step)
        QTimer.singleShot(60, step)
        QTimer.singleShot(200, lambda: native_keep(win, where(), centered))

    @staticmethod
    def _move_to_screen(win, scr):
        handle = win.windowHandle()
        if handle is not None and handle.screen() is not scr:
            handle.setScreen(scr)

    @staticmethod
    def _menu_anchor(menu):
        """⋯ 같은 버튼에서 연 메뉴면 그 버튼."""
        p = menu.parentWidget()
        if isinstance(p, QAbstractButton) and p.isVisible() and (p.isDown() or p.underMouse()):
            return p
        return None

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
    def keep_menu(cls, menu, anchor, cursor):
        if not menu.isVisible():
            return
        if anchor is not None:
            cls.place(menu, anchor)
            return
        scr = QApplication.screenAt(cursor)
        if scr is None:
            return
        cls._move_to_screen(menu, scr)           # 좌표가 맞아 보여도 모니터 소속은 항상 다시 정함
        avail = scr.availableGeometry()
        g = menu.geometry()
        if avail.contains(g):
            x, y = g.x(), g.y()
        else:
            x, y = cursor.x(), cursor.y()
        x = max(avail.left(), min(x, avail.right() - g.width() + 1))
        y = max(avail.top(), min(y, avail.bottom() - g.height() + 1))
        if (x, y) != (menu.x(), menu.y()):
            menu.move(x, y)

    @classmethod
    def place(cls, popup, anchor):
        """popup 을 anchor(드롭다운·버튼·날짜 칸) 바로 아래에 (자리 없으면 위에)."""
        if not popup.isVisible() or not anchor.isVisible():
            return
        top_left = anchor.mapToGlobal(QPoint(0, 0))
        scr = QApplication.screenAt(top_left + QPoint(anchor.width() // 2, anchor.height() // 2)) or anchor.screen()
        cls._move_to_screen(popup, scr)
        avail = scr.availableGeometry()
        is_combo = isinstance(anchor, QComboBox)
        w, h = (max(popup.width(), anchor.width()) if is_combo else popup.width()), popup.height()
        if h > avail.height():
            h = avail.height()
            popup.resize(w, h)
        x = min(max(top_left.x(), avail.left()), avail.right() - w + 1)
        y = top_left.y() + anchor.height()
        if y + h > avail.bottom() + 1:
            y = top_left.y() - h
        y = max(avail.top(), min(y, avail.bottom() - h + 1))
        if (x, y) != (popup.x(), popup.y()):
            popup.move(x, y)


def install(app):
    app._popup_fix = PopupScreenFix(app)
    app.installEventFilter(app._popup_fix)

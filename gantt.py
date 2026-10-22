"""일정표 창: 왼쪽 = 아이디어 목록, 오른쪽 = 날짜가 가로로 쭉 놓인 달력 위에 시작→목표 화살표 막대.

휠 = 위아래, Shift+휠 = 좌우, Ctrl+휠 = 확대·축소, 빈 곳 끌기 = 이동, 막대·줄 누르기 = 그 아이디어 열기.
막대 끌기 = 날짜 옮기기, 막대 왼쪽 끝 = 시작일, 화살표 끝 = 목표일, 날짜 없는 줄의 빈 곳 끌기 = 새 막대. Esc = 취소.
"""
from datetime import date, timedelta

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollBar, QToolTip,
    QVBoxLayout, QWidget,
)

import theme
from store import ACTIVE, QUADRANTS, quadrant

LEFT_W = 250        # 왼쪽 목록 너비
HEAD_H = 58         # 위 날짜 줄 높이
ROW_H = 34
DAY_W = 26          # 하루 너비 (확대·축소로 바뀜)
DAY_MIN, DAY_MAX = 6, 72
WEEKDAYS = "월화수목금토일"


def _d(s):
    return date.fromisoformat(s) if s else None


def _rgba(hex_, a):
    c = QColor(hex_)
    c.setAlpha(a)
    return c


EDGE = 7        # 막대 끝을 잡는 너비(px)


class GanttCanvas(QWidget):
    opened = Signal(str)
    datesEdited = Signal(str, object, object)   # uid, 시작일, 목표일 (date 또는 None)

    def __init__(self, hbar, vbar, parent=None):
        super().__init__(parent)
        self.hbar, self.vbar = hbar, vbar
        self.rows = []
        self.day_w = DAY_W
        self.lo = self.hi = date.today()
        self.hover = -1
        self.press = None           # (마우스 위치, h값, v값, 누른 줄)
        self.dragged = False
        self.edit = None            # 막대 끄는 중: {row, mode, s0, e0, s, e, px}
        self.setFocusPolicy(Qt.StrongFocus)     # Esc 받으려고
        self.setMouseTracking(True)
        self.setMinimumSize(500, 240)
        hbar.valueChanged.connect(self.update)
        vbar.valueChanged.connect(self.update)

    # ---------- 데이터 ----------
    def set_rows(self, rows):
        today = date.today()
        dated = [r for r in rows if r["start_date"] or r["due_date"]]
        undated = [r for r in rows if not (r["start_date"] or r["due_date"])]
        dated.sort(key=lambda r: (r["start_date"] or r["due_date"], r["due_date"] or "9999"))
        self.rows = dated + undated
        self.n_dated = len(dated)
        days = [today]
        for r in dated:
            for k in ("start_date", "due_date"):
                if r[k]:
                    days.append(_d(r[k]))
        self.lo = min(days) - timedelta(days=10)
        self.hi = max(max(days) + timedelta(days=30), self.lo + timedelta(days=90))
        self._update_bars()
        self.update()

    def total_days(self):
        return (self.hi - self.lo).days + 1

    def _update_bars(self):
        body_w = max(1, self.width() - LEFT_W)
        self.hbar.setRange(0, max(0, self.total_days() * self.day_w - body_w))
        self.hbar.setPageStep(body_w)
        self.hbar.setSingleStep(self.day_w)
        body_h = max(1, self.height() - HEAD_H)
        self.vbar.setRange(0, max(0, len(self.rows) * ROW_H - body_h))
        self.vbar.setPageStep(body_h)
        self.vbar.setSingleStep(ROW_H)

    def resizeEvent(self, ev):
        self._update_bars()
        super().resizeEvent(ev)

    # ---------- 좌표 ----------
    def x_of(self, d):
        return LEFT_W + (d - self.lo).days * self.day_w - self.hbar.value()

    def date_at(self, x):
        return self.lo + timedelta(days=int((x - LEFT_W + self.hbar.value()) // self.day_w))

    def row_y(self, i):
        return HEAD_H + i * ROW_H - self.vbar.value()

    def row_at(self, y):
        if y < HEAD_H:
            return -1
        i = int((y - HEAD_H + self.vbar.value()) // ROW_H)
        return i if 0 <= i < len(self.rows) else -1

    def go_today(self):
        body_w = self.width() - LEFT_W
        self.hbar.setValue(int((date.today() - self.lo).days * self.day_w - body_w * 0.25))

    def zoom(self, factor, anchor_x=None):
        if anchor_x is None:
            anchor_x = LEFT_W + (self.width() - LEFT_W) / 2
        day_pos = (anchor_x - LEFT_W + self.hbar.value()) / self.day_w     # 기준점의 날짜 위치
        self.day_w = max(DAY_MIN, min(DAY_MAX, int(round(self.day_w * factor))))
        self._update_bars()
        self.hbar.setValue(int(day_pos * self.day_w - (anchor_x - LEFT_W)))
        self.update()

    # ---------- 그리기 ----------
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        today = date.today()
        body = QRect(LEFT_W, HEAD_H, w - LEFT_W, h - HEAD_H)
        p.fillRect(self.rect(), QColor(theme.BASE))

        # 보이는 날짜 범위
        first = max(self.lo, self.date_at(LEFT_W))
        last = min(self.hi, self.date_at(w) + timedelta(days=1))

        p.save()
        p.setClipRect(body)
        # 주말 바탕, 날짜 세로선, 달 경계
        d = first
        while d <= last:
            x = self.x_of(d)
            if d.weekday() >= 5:
                p.fillRect(QRectF(x, HEAD_H, self.day_w, h), QColor(theme.ALT))
            if d.day == 1:
                p.setPen(QPen(QColor(theme.TEXT_OFF), 1))
            elif self.day_w >= 14 or d.weekday() == 0:
                p.setPen(QPen(QColor(theme.BORDER), 1, Qt.DotLine))
            else:
                d += timedelta(days=1)
                continue
            p.drawLine(QPointF(x, HEAD_H), QPointF(x, h))
            d += timedelta(days=1)
        # 오늘 칸
        tx = self.x_of(today)
        p.fillRect(QRectF(tx, HEAD_H, self.day_w, h), _rgba(theme.ACCENT, 26))

        # 줄
        for i, r in enumerate(self.rows):
            y = self.row_y(i)
            if y + ROW_H < HEAD_H or y > h:
                continue
            if i == self.hover:
                p.fillRect(QRectF(LEFT_W, y, w - LEFT_W, ROW_H), QColor(theme.ITEM_HOVER))
            p.setPen(QPen(QColor(theme.LINE), 1))
            p.drawLine(QPointF(LEFT_W, y + ROW_H), QPointF(w, y + ROW_H))
            if self.edit and self.edit["row"] == i:
                self._draw_bar(p, r, y, today, self.edit["s"], self.edit["e"], editing=True)
            else:
                self._draw_bar(p, r, y, today)

        # 오늘 선
        p.setPen(QPen(QColor(theme.DANGER), 1.5))
        p.drawLine(QPointF(tx + self.day_w / 2, HEAD_H), QPointF(tx + self.day_w / 2, h))
        p.restore()

        self._draw_header(p, first, last, today)
        self._draw_left(p, h)
        # 왼쪽 위 모서리
        p.fillRect(QRect(0, 0, LEFT_W, HEAD_H), QColor(theme.PANEL))
        p.setPen(QColor(theme.TEXT_DIM))
        p.drawText(QRect(14, 0, LEFT_W - 20, HEAD_H), Qt.AlignVCenter | Qt.AlignLeft,
                   "아이디어 %d개" % len(self.rows))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.drawLine(0, HEAD_H - 1, w, HEAD_H - 1)
        p.drawLine(LEFT_W - 1, 0, LEFT_W - 1, h)
        p.end()

    def _draw_header(self, p, first, last, today):
        w = self.width()
        p.save()
        p.setClipRect(QRect(LEFT_W, 0, w - LEFT_W, HEAD_H))
        p.fillRect(QRect(LEFT_W, 0, w - LEFT_W, HEAD_H), QColor(theme.PANEL))
        small = QFont(self.font())
        small.setPointSizeF(self.font().pointSizeF() * 0.85)
        bold = QFont(self.font())
        bold.setBold(True)

        # 1줄: 년·월 (달이 바뀌는 곳마다, 첫 달은 왼쪽 끝에 붙여서)
        d = first.replace(day=1)
        while d <= last:
            nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
            x1 = max(self.x_of(d), LEFT_W)
            x2 = self.x_of(nxt)
            if x2 > LEFT_W:
                p.setFont(bold)
                p.setPen(QColor(theme.TEXT))
                label = "%d년 %d월" % (d.year, d.month)
                if p.fontMetrics().horizontalAdvance(label) + 10 > x2 - x1:
                    label = "%d월" % d.month      # 자리가 좁으면 짧게, 그래도 모자라면 생략
                    if p.fontMetrics().horizontalAdvance(label) + 10 > x2 - x1:
                        label = ""
                p.drawText(QRectF(x1 + 6, 2, max(0, x2 - x1 - 8), 20), Qt.AlignVCenter | Qt.AlignLeft, label)
                p.setPen(QPen(QColor(theme.TEXT_OFF), 1))
                p.drawLine(QPointF(self.x_of(d), 0), QPointF(self.x_of(d), HEAD_H))
            d = nxt

        # 2줄: 날짜 (좁으면 월요일만), 3줄: 요일 (넓을 때만)
        p.setFont(small)
        every = 1 if self.day_w >= 20 else 7
        d = first
        while d <= last:
            x = self.x_of(d)
            if every == 1 or d.weekday() == 0:
                if d == today:
                    col = theme.ON_ACCENT
                elif d.weekday() == 6:
                    col = theme.QUAD[1]
                elif d.weekday() == 5:
                    col = theme.QUAD[2]
                else:
                    col = theme.TEXT_DIM
                if d == today:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(theme.ACCENT))
                    p.drawRoundedRect(QRectF(x + 1, 22, max(self.day_w, 22) - 2, HEAD_H - 24), theme.r(4), theme.r(4))
                p.setPen(QColor(col))
                cw = max(self.day_w, 22)
                p.drawText(QRectF(x, 22, cw, 18), Qt.AlignCenter, str(d.day))
                if self.day_w >= 20:
                    p.drawText(QRectF(x, 38, cw, 16), Qt.AlignCenter, WEEKDAYS[d.weekday()])
            d += timedelta(days=1)
        p.restore()

    def _draw_left(self, p, h):
        p.save()
        p.setClipRect(QRect(0, HEAD_H, LEFT_W, h - HEAD_H))
        p.fillRect(QRect(0, HEAD_H, LEFT_W, h - HEAD_H), QColor(theme.SIDEBAR))
        fm = self.fontMetrics()
        for i, r in enumerate(self.rows):
            y = self.row_y(i)
            if y + ROW_H < HEAD_H or y > h:
                continue
            if i == self.n_dated and i > 0:     # 여기부터 날짜 없는 것
                p.setPen(QPen(QColor(theme.BORDER), 1, Qt.DashLine))
                p.drawLine(QPointF(0, y), QPointF(self.width(), y))
            if i == self.hover:
                p.fillRect(QRectF(0, y, LEFT_W, ROW_H), QColor(theme.ITEM_HOVER))
            q = quadrant(r["importance"], r["urgency"])
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.QUAD[q]))
            if q:
                p.drawEllipse(QRectF(14, y + ROW_H / 2 - 4, 8, 8))
            else:
                p.setBrush(Qt.NoBrush)
                p.setPen(QColor(theme.QUAD[0]))
                p.drawEllipse(QRectF(14, y + ROW_H / 2 - 4, 8, 8))
            right = LEFT_W - 10
            st = r["status"]
            if st != "보관함":
                sw = fm.horizontalAdvance(st)
                p.setPen(QColor(theme.TEXT_DIM))
                p.drawText(QRectF(right - sw, y, sw, ROW_H), Qt.AlignVCenter | Qt.AlignRight, st)
                right -= sw + 8
            dim = st in ("완료", "보류")
            p.setPen(QColor(theme.TEXT_DIM if dim else theme.TEXT))
            tw = right - 30
            p.drawText(QRectF(30, y, tw, ROW_H), Qt.AlignVCenter | Qt.AlignLeft,
                       fm.elidedText(r["title"] or "(제목 없음)", Qt.ElideRight, int(tw)))
        p.restore()

    def _draw_bar(self, p, r, y, today, s=None, e=None, editing=False):
        if not editing:
            s, e = _d(r["start_date"]), _d(r["due_date"])
        q = quadrant(r["importance"], r["urgency"])
        col = QColor(theme.QUAD[q] if q else theme.QUAD[4])
        done = r["status"] == "완료"
        paused = r["status"] == "보류"
        if done or paused:
            col.setAlpha(110)
        cy = y + ROW_H / 2
        bh = 16
        fm = self.fontMetrics()
        p.setFont(self.font())

        if s and e and e >= s:
            x1, x2 = self.x_of(s), self.x_of(e + timedelta(days=1))
            head = min(10, max(4, (x2 - x1) / 3))
            path = QPainterPath()
            path.moveTo(x1, cy - bh / 2)
            path.lineTo(x2 - head, cy - bh / 2)
            path.lineTo(x2 - head, cy - bh / 2 - 4)
            path.lineTo(x2, cy)
            path.lineTo(x2 - head, cy + bh / 2 + 4)
            path.lineTo(x2 - head, cy + bh / 2)
            path.lineTo(x1, cy + bh / 2)
            path.closeSubpath()
            fill = QColor(col)
            fill.setAlpha(min(col.alpha(), 170))
            overdue = not done and e < today
            p.setPen(QPen(QColor(theme.TEXT), 2) if editing else
                     QPen(QColor(theme.DANGER), 2) if overdue else QPen(col, 1.2))
            p.setBrush(fill)
            p.drawPath(path)
            # 시작 쪽 세로 막대
            p.setPen(QPen(col.lighter(130), 2.5))
            p.drawLine(QPointF(x1, cy - bh / 2 - 3), QPointF(x1, cy + bh / 2 + 3))
            days = (e - s).days + 1
            text = "%s → %s · %d일%s" % (s.strftime("%m/%d"), e.strftime("%m/%d"), days, "  · 완료" if done else "")
            tw = fm.horizontalAdvance(text)
            tx1 = max(x1, LEFT_W)       # 막대가 왼쪽 밖에서 시작하면 보이는 곳부터 글씨
            if tw + 16 < x2 - tx1 - head:
                p.setPen(QColor("#ffffff" if theme.DARK else theme.TEXT))
                p.drawText(QRectF(tx1 + 8, cy - 10, x2 - tx1 - head - 8, 20), Qt.AlignVCenter | Qt.AlignLeft, text)
            else:
                p.setPen(QColor(theme.TEXT_DIM))
                p.drawText(QRectF(x2 + 6, cy - 10, tw + 4, 20), Qt.AlignVCenter | Qt.AlignLeft, text)
        elif s:
            # 시작만 있음: 점선 화살표 + '끝 미정'
            x1 = self.x_of(s)
            x2 = x1 + max(self.day_w * 10, 90)
            p.setPen(QPen(col, 2.5))
            p.drawLine(QPointF(x1, cy - bh / 2 - 3), QPointF(x1, cy + bh / 2 + 3))
            p.setPen(QPen(col, 2, Qt.DashLine))
            p.drawLine(QPointF(x1, cy), QPointF(x2 - 6, cy))
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawPolygon(QPolygonF([QPointF(x2 - 8, cy - 5), QPointF(x2, cy), QPointF(x2 - 8, cy + 5)]))
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(QRectF(x2 + 6, cy - 10, 200, 20), Qt.AlignVCenter | Qt.AlignLeft,
                       "%s 시작 · 끝 미정" % s.strftime("%m/%d"))
        elif e:
            # 목표일만 있음: ◆
            xc = self.x_of(e) + self.day_w / 2
            p.setPen(QPen(QColor(theme.DANGER), 2) if (not done and e < today) else QPen(col.lighter(120), 1))
            p.setBrush(col)
            p.drawPolygon(QPolygonF([QPointF(xc, cy - 8), QPointF(xc + 8, cy), QPointF(xc, cy + 8), QPointF(xc - 8, cy)]))
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(QRectF(xc + 12, cy - 10, 200, 20), Qt.AlignVCenter | Qt.AlignLeft,
                       "목표 %s · 시작 미정" % e.strftime("%m/%d"))
        else:
            p.setPen(QColor(theme.TEXT_OFF))
            p.drawText(QRectF(LEFT_W + 12, cy - 10, 400, 20), Qt.AlignVCenter | Qt.AlignLeft,
                       "날짜 없음 — 눌러서 아이디어 화면에서 시작일·목표일을 정해요")

    # ---------- 마우스 ----------
    def wheelEvent(self, ev):
        dy = ev.angleDelta().y()
        if ev.modifiers() & Qt.ControlModifier:
            self.zoom(1.2 if dy > 0 else 1 / 1.2, ev.position().x())
        elif ev.modifiers() & Qt.ShiftModifier or ev.angleDelta().x():
            self.hbar.setValue(self.hbar.value() - (dy or ev.angleDelta().x()))
        else:
            self.vbar.setValue(self.vbar.value() - dy // 2)

    def hit(self, pos):
        """pos 에 있는 막대 부분: (줄, 'move'|'start'|'end'|'new') 또는 (줄, None)."""
        i = self.row_at(pos.y())
        if i < 0 or pos.x() < LEFT_W:
            return i, None
        r = self.rows[i]
        cy = self.row_y(i) + ROW_H / 2
        near = abs(pos.y() - cy) <= 13
        x = pos.x()
        s, e = _d(r["start_date"]), _d(r["due_date"])
        if s and e and e >= s:
            x1, x2 = self.x_of(s), self.x_of(e + timedelta(days=1))
            if near and abs(x - x2) <= EDGE + 2:
                return i, "end"
            if near and abs(x - x1) <= EDGE:
                return i, "start"
            if near and x1 < x < x2:
                return i, "move"
        elif s:
            x1 = self.x_of(s)
            tip = x1 + max(self.day_w * 10, 90)
            if near and abs(x - tip) <= 12:
                return i, "end"             # 점선 화살표 끝을 끌면 목표일이 생김
            if near and x1 - EDGE <= x < tip - 12:
                return i, "move"
        elif e:
            xc = self.x_of(e) + self.day_w / 2
            if near and abs(x - xc) <= 11:
                return i, "move"
        else:
            return i, "new"                 # 날짜 없는 줄: 빈 곳을 끌어 새 막대
        return i, None

    CURSORS = {"move": Qt.SizeAllCursor, "start": Qt.SizeHorCursor, "end": Qt.SizeHorCursor, "new": Qt.CrossCursor}

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            pos = ev.position()
            self.press = (pos, self.hbar.value(), self.vbar.value(), self.row_at(pos.y()))
            self.dragged = False
            i, mode = self.hit(pos)
            if mode:
                r = self.rows[i]
                s, e = _d(r["start_date"]), _d(r["due_date"])
                if mode == "new":
                    s = e = self.date_at(pos.x())
                self.edit = {"row": i, "mode": mode, "s0": s, "e0": e, "s": s, "e": e, "px": pos.x(),
                             "d0": self.date_at(pos.x())}

    def mouseMoveEvent(self, ev):
        pos = ev.position()
        if self.edit and self.press:
            ed = self.edit
            if not self.dragged and abs(pos.x() - ed["px"]) < 4:
                return
            self.dragged = True
            days = (self.date_at(pos.x()) - ed["d0"]).days
            s0, e0 = ed["s0"], ed["e0"]
            one = timedelta(days=1)
            if ed["mode"] == "move":
                ed["s"] = s0 + timedelta(days=days) if s0 else None
                ed["e"] = e0 + timedelta(days=days) if e0 else None
            elif ed["mode"] == "start":
                ed["s"] = min(s0 + timedelta(days=days), e0)
            elif ed["mode"] == "end":
                base = e0 if e0 else s0 + timedelta(days=max(10, int(90 / self.day_w + 0.99)) - 1)
                ed["e"] = max(base + timedelta(days=days), s0)
            elif ed["mode"] == "new":
                d = self.date_at(pos.x())
                ed["s"], ed["e"] = min(ed["d0"], d), max(ed["d0"], d)
            self.update()
            QToolTip.showText(ev.globalPosition().toPoint(), self._edit_tip(ed), self)
            return
        if self.press:
            start, hv, vv, _row = self.press
            delta = pos - start
            if self.dragged or abs(delta.x()) + abs(delta.y()) > 6:
                self.dragged = True
                self.setCursor(Qt.ClosedHandCursor)
                self.hbar.setValue(int(hv - delta.x()))
                self.vbar.setValue(int(vv - delta.y()))
                return
        i, mode = self.hit(pos)
        self.setCursor(self.CURSORS.get(mode, Qt.PointingHandCursor if i >= 0 else Qt.ArrowCursor))
        if i != self.hover:
            self.hover = i
            self.update()
        if i >= 0:
            QToolTip.showText(ev.globalPosition().toPoint(), self._tip(self.rows[i]), self)
        else:
            QToolTip.hideText()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.LeftButton or not self.press:
            return
        ed, self.edit = self.edit, None
        if ed and self.dragged:
            self.press, self.dragged = None, False
            self.update()
            if (ed["s"], ed["e"]) != (ed["s0"], ed["e0"]):
                self.datesEdited.emit(self.rows[ed["row"]]["uuid"], ed["s"], ed["e"])
            return
        row = self.press[3]
        dragged = self.dragged
        self.press, self.dragged = None, False
        self.setCursor(Qt.PointingHandCursor if self.hover >= 0 else Qt.ArrowCursor)
        if not dragged and row >= 0 and row == self.row_at(ev.position().y()):
            self.opened.emit(self.rows[row]["uuid"])

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape and self.edit:
            self.edit, self.press, self.dragged = None, None, False     # 끄던 것 취소
            QToolTip.hideText()
            self.update()
            return
        super().keyPressEvent(ev)

    def _edit_tip(self, ed):
        s, e = ed["s"], ed["e"]
        if s and e:
            return "%s → %s (%d일)" % (s.isoformat(), e.isoformat(), (e - s).days + 1)
        if s:
            return "시작 %s" % s.isoformat()
        return "목표 %s" % e.isoformat()

    def leaveEvent(self, ev):
        self.hover = -1
        self.update()
        super().leaveEvent(ev)

    def _tip(self, r):
        lines = [r["title"] or "(제목 없음)"]
        s, e = _d(r["start_date"]), _d(r["due_date"])
        if s and e:
            lines.append("%s → %s (%d일)" % (s.isoformat(), e.isoformat(), (e - s).days + 1))
        elif s:
            lines.append("시작 %s · 끝 미정" % s.isoformat())
        elif e:
            lines.append("목표 %s · 시작 미정" % e.isoformat())
        else:
            lines.append("날짜 없음")
        if e and r["status"] != "완료":
            n = (e - date.today()).days
            lines.append("목표까지 %d일 남음" % n if n > 0 else "오늘이 목표일" if n == 0 else "%d일 지남" % -n)
        lines.append("상태: %s · %s%s" % (r["status"], QUADRANTS[quadrant(r["importance"], r["urgency"])],
                                        " · 분류: " + r["category"] if r["category"] else ""))
        return "\n".join(lines)


class GanttWindow(QDialog):
    opened = Signal(str)
    changed = Signal(str)       # 막대를 끌어 날짜를 바꿈 (uid)

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.setWindowTitle("일정표 — 아이디어 보드")
        self.setWindowFlags(Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.resize(1200, 640)

        self.hbar = QScrollBar(Qt.Horizontal)
        self.vbar = QScrollBar(Qt.Vertical)
        self.canvas = GanttCanvas(self.hbar, self.vbar)
        self.canvas.opened.connect(self.opened)
        self.canvas.datesEdited.connect(self._save_dates)

        today = QPushButton("오늘로")
        today.clicked.connect(self.canvas.go_today)
        zin = QPushButton("+")
        zout = QPushButton("-")
        for b, f, tip in ((zin, 1.3, "크게 (Ctrl+휠)"), (zout, 1 / 1.3, "작게 (Ctrl+휠)")):
            b.setFixedWidth(34)
            b.setToolTip(tip)
            b.clicked.connect(lambda _c=False, f=f: self.canvas.zoom(f))
        self.show_done = QCheckBox("완료도 보기")
        self.show_done.toggled.connect(self.refresh)
        hint = QLabel("막대 끌기: 날짜 옮기기 · 양 끝 끌기: 시작일·목표일 · 빈 곳 끌기: 화면 이동 · "
                      "Ctrl+휠: 확대 · 누르면 아이디어 열기")
        hint.setStyleSheet("color:%s;" % theme.TEXT_DIM)

        bar = QHBoxLayout()
        bar.addWidget(today)
        bar.addSpacing(6)
        bar.addWidget(zout)
        bar.addWidget(zin)
        bar.addSpacing(12)
        bar.addWidget(self.show_done)
        bar.addStretch(1)
        bar.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(0)
        grid.addWidget(self.canvas, 0, 0)
        grid.addWidget(self.vbar, 0, 1)
        grid.addWidget(self.hbar, 1, 0)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)
        lay.addLayout(bar)
        lay.addLayout(grid, 1)
        self._first = True

    def _save_dates(self, uid, s, e):
        self.store.update(uid, start_date=s.isoformat() if s else None, due_date=e.isoformat() if e else None)
        self.refresh()
        self.changed.emit(uid)

    def refresh(self):
        # 일정표엔 '진행 중'이거나 목표일을 정한 것만 (나중에 할 것까지 다 나오면 복잡해서)
        rows = [r for r in self.store.ideas()
                if (r["status"] == ACTIVE or r["due_date"])
                and (self.show_done.isChecked() or r["status"] != "완료")]
        c = self.canvas
        left = c.date_at(LEFT_W)            # 보고 있던 왼쪽 끝 날짜 (날짜 범위가 바뀌어도 같은 곳을 보게)
        v = self.vbar.value()
        c.set_rows(rows)
        if not self._first:
            self.hbar.setValue((left - c.lo).days * c.day_w)
            self.vbar.setValue(v)

    def showEvent(self, ev):
        super().showEvent(ev)
        # 닫혀 있던 동안 바뀐 것(새 아이디어·날짜)도 보이게 열 때마다 새로 읽음
        first = self._first
        self.refresh()
        if first:
            self._first = False
            self.canvas.go_today()

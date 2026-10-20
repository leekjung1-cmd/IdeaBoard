"""대시보드: x = 중요도, y = 긴급도 (1~5) 좌표 위에 아이디어를 점(칩)으로 놓는다.

칩을 끌어서 다른 칸에 놓으면 중요도·긴급도가 바뀌고, 아래 '미분류' 칸에 놓으면 둘 다 지운다.
"""
from datetime import date, datetime
from html import escape

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QToolTip, QVBoxLayout,
    QWidget,
)

import theme
from todo import PAPER, dday as todo_dday
from store import ACTIVE, ACTIVE_LIMIT, HIGH, QUADRANTS, STATUSES, quadrant


def weekly_tonight(store_):
    from weekly import tonight      # weekly 가 dashboard 를 안 쓰지만 순서 꼬임 방지로 여기서
    return tonight(store_)

LEVELS = 5
CHIP_H = 24
CHIP_H2 = 40        # 다음 한 걸음이 있는 칩 (두 줄)
CHIP_GAP = 4


def chip_h(r):
    return CHIP_H2 if r is not None and r["next_step"] else CHIP_H


def _rgba(hex_, a):
    c = QColor(hex_)
    c.setAlpha(a)
    return c


class Chip:
    """화면에 그려진 칩 하나 (아이디어 또는 '+N개 더')."""

    def __init__(self, rect, row=None, more=None):
        self.rect = rect
        self.row = row          # sqlite Row (아이디어)
        self.more = more        # '+N개 더' 칩이면 숨겨진 Row 목록


class MatrixChart(QWidget):
    opened = Signal(str)
    moved = Signal(str, object, object)      # uid, 중요도, 긴급도 (None = 미분류)

    PAD_L, PAD_R, PAD_T, PAD_B = 74, 12, 12, 46
    TRAY_H = 64

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.chips = []
        self.hover = None           # 마우스가 올라간 Chip
        self.press = None           # (Chip, 누른 위치)
        self.drag_pos = None        # 끄는 중이면 마우스 위치
        self.setMouseTracking(True)
        self.setMinimumSize(420, 400)

    # ---------- 좌표 ----------
    def plot_rect(self):
        return QRect(self.PAD_L, self.PAD_T,
                     self.width() - self.PAD_L - self.PAD_R,
                     self.height() - self.PAD_T - self.PAD_B - self.TRAY_H - 10)

    def tray_rect(self):
        p = self.plot_rect()
        return QRect(p.left(), self.height() - self.TRAY_H - 4, p.width(), self.TRAY_H)

    def cell_rect(self, imp, urg):
        p = self.plot_rect()
        cw, ch = p.width() / LEVELS, p.height() / LEVELS
        return QRectF(p.left() + (imp - 1) * cw, p.top() + (LEVELS - urg) * ch, cw, ch).toRect()

    def target_at(self, pos):
        """놓을 자리: (중요도, 긴급도) / ('tray',) / None."""
        p = self.plot_rect()
        if p.contains(pos):
            imp = min(LEVELS, int((pos.x() - p.left()) / (p.width() / LEVELS)) + 1)
            urg = LEVELS - min(LEVELS - 1, int((pos.y() - p.top()) / (p.height() / LEVELS)))
            return (imp, urg)
        if self.tray_rect().adjusted(0, -6, 0, 6).contains(pos):
            return ("tray",)
        return None

    # ---------- 배치 ----------
    def set_rows(self, rows):
        self.rows = list(rows)
        self._layout()
        self.update()

    def resizeEvent(self, ev):
        self._layout()
        super().resizeEvent(ev)

    def _chip_width(self, text, room):
        fm = self.fontMetrics()
        return int(min(room, fm.horizontalAdvance(text) + 38))

    def _layout(self):
        self.chips = []
        cells, tray = {}, []
        for r in self.rows:
            if r["importance"] is None or r["urgency"] is None:
                tray.append(r)
            else:
                cells.setdefault((r["importance"], r["urgency"]), []).append(r)

        for (imp, urg), rows in cells.items():
            cell = self.cell_rect(imp, urg).adjusted(4, 4, -4, -4)

            def height(rs, more):
                hs = [chip_h(r) for r in rs] + ([CHIP_H] if more else [])
                return sum(hs) + CHIP_GAP * max(0, len(hs) - 1)

            shown, hidden = list(rows), []
            while len(shown) > 1 and height(shown, bool(hidden)) > cell.height():
                hidden.insert(0, shown.pop())
            if hidden and len(shown) == 1 and height(shown, True) > cell.height():
                shown, hidden = [], list(rows)
            y = cell.center().y() - height(shown, bool(hidden)) // 2
            for r in shown:
                text = r["title"] or "(제목 없음)"
                if r["next_step"]:
                    text = max(text, "👣 " + r["next_step"], key=len)
                w = self._chip_width(text, cell.width())
                h = chip_h(r)
                self.chips.append(Chip(QRect(cell.center().x() - w // 2, y, w, h), row=r))
                y += h + CHIP_GAP
            if hidden:
                w = self._chip_width("+%d개 더" % len(hidden), cell.width())
                self.chips.append(Chip(QRect(cell.center().x() - w // 2, y, w, CHIP_H), more=hidden))

        t = self.tray_rect().adjusted(10, 28, -10, -8)
        x = t.left()
        for i, r in enumerate(tray):
            w = self._chip_width(r["title"] or "(제목 없음)", 220)
            if x + w > t.right():
                rest = tray[i:]
                w2 = self._chip_width("+%d개 더" % len(rest), 120)
                self.chips.append(Chip(QRect(min(x, t.right() - w2), t.top(), w2, CHIP_H), more=rest))
                break
            self.chips.append(Chip(QRect(x, t.top(), w, CHIP_H), row=r))
            x += w + 6

    def chip_at(self, pos):
        for c in reversed(self.chips):
            if c.rect.contains(pos):
                return c
        return None

    # ---------- 그리기 ----------
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        plot = self.plot_rect()
        cw, ch = plot.width() / LEVELS, plot.height() / LEVELS
        # 가운데(3)를 기준으로 좌우·위아래 대칭. 3 에 있는 아이디어는 선 위에 놓임
        split_x = plot.left() + plot.width() / 2
        split_y = plot.top() + plot.height() / 2

        # 사분면 영역 바탕
        regions = {
            1: QRectF(split_x, plot.top(), plot.right() - split_x, split_y - plot.top()),
            3: QRectF(plot.left(), plot.top(), split_x - plot.left(), split_y - plot.top()),
            2: QRectF(split_x, split_y, plot.right() - split_x, plot.bottom() - split_y),
            4: QRectF(plot.left(), split_y, split_x - plot.left(), plot.bottom() - split_y),
        }
        for q, r in regions.items():
            p.fillRect(r, _rgba(theme.QUAD[q], 26))
        # 사분면 이름 (바깥쪽 모서리)
        f = QFont(self.font())
        f.setBold(True)
        p.setFont(f)
        for q, r in regions.items():
            p.setPen(_rgba(theme.QUAD[q], 200))
            align = (Qt.AlignTop if q in (1, 3) else Qt.AlignBottom) | (Qt.AlignRight if q in (1, 2) else Qt.AlignLeft)
            p.drawText(r.adjusted(8, 5, -8, -5), align, QUADRANTS[q])
        p.setFont(self.font())

        # 눈금 선 (1·2·4·5 를 지나는 점선, 3 은 가운데 굵은 선)
        p.setPen(QPen(QColor(theme.BORDER), 1, Qt.DotLine))
        for i in range(1, LEVELS + 1):
            if i == (LEVELS + 1) // 2:
                continue
            x = plot.left() + (i - 0.5) * cw
            y = plot.top() + (i - 0.5) * ch
            p.drawLine(QPoint(int(x), plot.top()), QPoint(int(x), plot.bottom()))
            p.drawLine(QPoint(plot.left(), int(y)), QPoint(plot.right(), int(y)))
        p.setPen(QPen(QColor("#6a6a6a"), 1.5))
        p.drawLine(QPoint(int(split_x), plot.top()), QPoint(int(split_x), plot.bottom()))
        p.drawLine(QPoint(plot.left(), int(split_y)), QPoint(plot.right(), int(split_y)))
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(plot)

        # 눈금·축 이름
        p.setPen(QColor(theme.TEXT_DIM))
        for i in range(1, LEVELS + 1):
            cx = plot.left() + (i - 0.5) * cw
            p.drawText(QRectF(cx - 20, plot.bottom() + 4, 40, 18), Qt.AlignCenter, str(i))
            cy = plot.top() + (LEVELS - i + 0.5) * ch
            p.drawText(QRectF(plot.left() - 26, cy - 9, 20, 18), Qt.AlignRight | Qt.AlignVCenter, str(i))
        p.setPen(QColor(theme.TEXT))
        p.drawText(QRectF(plot.left(), plot.bottom() + 22, plot.width(), 20), Qt.AlignCenter, "중요도  →")
        p.drawText(QRectF(0, plot.center().y() - 22, plot.left() - 24, 44), Qt.AlignCenter, "↑\n긴급도")

        # 미분류 칸
        tray = self.tray_rect()
        p.setPen(QPen(QColor(theme.BORDER), 1, Qt.DashLine))
        p.setBrush(QColor(255, 255, 255, 6))
        p.drawRoundedRect(tray, 8, 8)
        p.setPen(QColor(theme.TEXT_DIM))
        p.drawText(tray.adjusted(12, 6, -12, 0), Qt.AlignLeft | Qt.AlignTop,
                   "미분류 — 중요도·긴급도 안 정함 (칩을 여기로 끌어오면 둘 다 지워요)")

        # 끄는 중이면 놓일 자리 강조
        target = self.target_at(self.drag_pos) if self.drag_pos is not None else None
        if target:
            r = tray if target == ("tray",) else self.cell_rect(*target)
            p.setPen(QPen(QColor(theme.ACCENT), 2))
            p.setBrush(_rgba(theme.ACCENT, 30))
            p.drawRoundedRect(QRectF(r).adjusted(2, 2, -2, -2), 6, 6)

        dragging = self.press[0] if (self.press and self.drag_pos is not None) else None
        for c in self.chips:
            self._draw_chip(p, c, c.rect, faded=c is dragging)
        if dragging is not None:
            r = QRect(dragging.rect)
            r.moveCenter(self.drag_pos)
            self._draw_chip(p, dragging, r)
        p.end()

    def _draw_chip(self, p, c, rect, faded=False):
        hover = c is self.hover and self.drag_pos is None
        p.save()
        if faded:
            p.setOpacity(0.3)
        if c.more is not None:
            p.setPen(QPen(QColor(theme.BORDER), 1))
            p.setBrush(QColor(theme.ITEM_HOVER if hover else theme.PANEL))
            p.drawRoundedRect(QRectF(rect), CHIP_H / 2, CHIP_H / 2)
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(rect, Qt.AlignCenter, "+%d개 더" % len(c.more))
            p.restore()
            return
        r = c.row
        q = quadrant(r["importance"], r["urgency"])
        col = theme.QUAD[q]
        active = r["status"] == ACTIVE
        p.setPen(QPen(QColor(theme.ACCENT) if active and not hover else _rgba(col, 230 if hover else 150),
                      1.8 if active else 1.2))
        p.setBrush(QColor(theme.ITEM_SEL if hover else "#2a2b2e"))
        two = rect.height() > CHIP_H
        radius = 9 if two else CHIP_H / 2
        p.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        top = QRect(rect.left(), rect.top() + (2 if two else 0), rect.width(), CHIP_H - (4 if two else 0))
        dot = QRectF(rect.left() + 9, top.center().y() - 3.5, 8, 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(col))
        p.drawEllipse(dot)
        dim = r["status"] in ("보류",)
        p.setPen(QColor(theme.TEXT_DIM if dim else theme.TEXT))
        tr = top.adjusted(22, 0, -10, 0)
        fm = self.fontMetrics()
        p.drawText(tr, Qt.AlignVCenter | Qt.AlignLeft, fm.elidedText(r["title"] or "(제목 없음)", Qt.ElideRight, tr.width()))
        if two:     # 둘째 줄: 다음 한 걸음
            sr = QRect(rect.left() + 10, top.bottom() - 1, rect.width() - 18, rect.bottom() - top.bottom() - 2)
            f = p.font()
            f.setPointSizeF(f.pointSizeF() - 1)
            p.setFont(f)
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(sr, Qt.AlignVCenter | Qt.AlignLeft,
                       QFontMetrics(f).elidedText("👣 " + r["next_step"], Qt.ElideRight, sr.width()))
        if r["due_date"] and r["due_date"] <= date.today().isoformat():     # 목표일 오늘이거나 지남
            p.setPen(QPen(QColor(theme.BASE), 1.5))
            p.setBrush(QColor(theme.DANGER))
            p.drawEllipse(QRectF(rect.right() - 7, rect.top() - 3, 10, 10))
        p.restore()

    # ---------- 마우스 ----------
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            c = self.chip_at(ev.position().toPoint())
            self.press = (c, ev.position().toPoint()) if c else None

    def mouseMoveEvent(self, ev):
        pos = ev.position().toPoint()
        if self.press and self.press[0].row is not None:
            if self.drag_pos is not None or \
                    (pos - self.press[1]).manhattanLength() >= QApplication.startDragDistance():
                self.drag_pos = pos
                self.setCursor(Qt.ClosedHandCursor)
                self.update()
                return
        c = self.chip_at(pos)
        if c is not self.hover:
            self.hover = c
            self.setCursor(Qt.PointingHandCursor if c else Qt.ArrowCursor)
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.LeftButton or not self.press:
            return
        chip, _ = self.press
        pos = ev.position().toPoint()
        was_drag = self.drag_pos is not None
        self.press, self.drag_pos = None, None
        self.setCursor(Qt.PointingHandCursor if self.chip_at(pos) else Qt.ArrowCursor)
        self.update()
        if was_drag:
            target = self.target_at(pos)
            if not target:
                return
            imp, urg = (None, None) if target == ("tray",) else target
            r = chip.row
            if (imp, urg) != (r["importance"], r["urgency"]):
                self.moved.emit(r["uuid"], imp, urg)
        elif chip.more is not None:
            m = QMenu(self)
            for r in chip.more:
                a = m.addAction(r["title"] or "(제목 없음)")
                a.setData(r["uuid"])
            a = m.exec(self.mapToGlobal(chip.rect.bottomLeft()))
            if a:
                self.opened.emit(a.data())
        elif chip.row is not None:
            self.opened.emit(chip.row["uuid"])

    def leaveEvent(self, ev):
        if self.hover is not None:
            self.hover = None
            self.update()
        super().leaveEvent(ev)

    def event(self, ev):
        if ev.type() == QEvent.ToolTip:
            c = self.chip_at(ev.pos())
            if c and c.row is not None and self.drag_pos is None:
                r = c.row
                lines = [r["title"] or "(제목 없음)"]
                if r["summary"]:
                    lines.append(r["summary"])
                if r["next_step"]:
                    lines.append("👣 다음 한 걸음: " + r["next_step"])
                info = "상태: %s" % r["status"] + ("  ·  분류: %s" % r["category"] if r["category"] else "")
                if r["importance"] is not None:
                    info += "  ·  중요도 %d  ·  긴급도 %d" % (r["importance"], r["urgency"])
                if r["due_date"]:
                    info += "  ·  목표 %s (%s)" % (r["due_date"], dday(r["due_date"], date.today())[0])
                lines.append(info)
                QToolTip.showText(ev.globalPos(), "\n".join(lines), self)
            elif c and c.more is not None:
                QToolTip.showText(ev.globalPos(), "\n".join(r["title"] or "(제목 없음)" for r in c.more), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(ev)


# ---------------------------------------------------------------- 일정 목록

def dday(date_str, today):
    """('D-3' 같은 글자, 색)"""
    d = (date.fromisoformat(date_str) - today).days
    if d < 0:
        return "%d일 지남" % -d, theme.DANGER
    if d == 0:
        return "오늘", theme.DANGER
    if d <= 7:
        return "D-%d" % d, theme.QUAD[3]
    return "D-%d" % d, theme.TEXT_DIM


STALE_DAYS = 7      # 이 날 수 넘게 안 건드리면 '오래 손 안 댄 것'


def ago(ms, today):
    """마지막으로 손댄 뒤 지난 날 수, 글자, 색."""
    n = (today - datetime.fromtimestamp(ms / 1000).date()).days
    text = "오늘 손댐" if n <= 0 else "어제 손댐" if n == 1 else "%d일 전 손댐" % n
    color = theme.DANGER if n >= 30 else theme.QUAD[3] if n >= STALE_DAYS else theme.TEXT_OFF
    return n, text, color


class ScheduleRow(QFrame):
    clicked = Signal(str)

    def __init__(self, row, badge, color, sub, parent=None, step=True):
        super().__init__(parent)
        self.uid = row["uuid"]
        self.setObjectName("srow")
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("#srow { border-radius:6px; } #srow:hover { background:%s; }" % theme.ITEM_HOVER)
        q = quadrant(row["importance"], row["urgency"])
        dot = QLabel("●")
        dot.setStyleSheet("color:%s;" % theme.QUAD[q])
        title = QLabel(row["title"] or "(제목 없음)")
        title.setMinimumWidth(10)
        title.setToolTip(row["title"] or "")
        date_ = QLabel(sub)         # sub 는 서식 있는 글 (날짜 · 며칠 전)
        date_.setTextFormat(Qt.RichText)
        date_.setStyleSheet("color:%s;" % theme.TEXT_DIM)
        b = QLabel(badge)
        b.setStyleSheet("color:%s; font-weight:bold;" % color)
        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(dot)
        top.addWidget(title, 1)
        top.addWidget(b)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(1)
        lay.addLayout(top)
        if sub:
            lay.addWidget(date_)
        self._step = None
        if step and row["next_step"]:
            self._step = QLabel()
            self._step.setMinimumWidth(10)
            self._step.setStyleSheet("color:%s;" % theme.TEXT)
            self._step_full = "👣 " + row["next_step"]
            self._step.setToolTip(self._step_full)
            lay.addWidget(self._step)
        elif step and row["status"] == ACTIVE:
            warn = QLabel("👣 다음 한 걸음을 적어 주세요")
            warn.setStyleSheet("color:%s;" % theme.QUAD[3])
            lay.addWidget(warn)
        self._title = title
        self._full = row["title"] or "(제목 없음)"

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        fm = self._title.fontMetrics()
        self._title.setText(fm.elidedText(self._full, Qt.ElideRight, max(20, self._title.width())))
        if self._step is not None:
            self._step.setText(fm.elidedText(self._step_full, Qt.ElideRight, max(20, self.width() - 20)))

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.rect().contains(ev.position().toPoint()):
            self.clicked.emit(self.uid)


class SchedulePanel(QFrame):
    """목표일 가까운 순 (지난 것 맨 위) + 곧 시작할 것."""
    opened = Signal(str)
    expandRequested = Signal()
    reviewRequested = Signal()
    timetableRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sched")
        self.setStyleSheet("#sched { background:%s; border:1px solid %s; border-radius:10px; }"
                           % (theme.SIDEBAR, theme.BORDER))
        head = QPushButton("일정   ⤢ 일정표")
        head.setToolTip("달력 위에 시작→목표 막대로 크게 보기 (Ctrl+T)")
        head.setCursor(Qt.PointingHandCursor)
        f = head.font()
        f.setPointSize(12)
        f.setBold(True)
        head.setFont(f)
        head.setStyleSheet("QPushButton { text-align:left; border:none; background:transparent; padding:2px 4px; }"
                           "QPushButton:hover { color:%s; background:%s; border-radius:5px; }"
                           % (theme.ACCENT, theme.ITEM_HOVER))
        head.clicked.connect(self.expandRequested)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background:transparent; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 6, 8)
        lay.setSpacing(6)
        lay.addWidget(head)
        lay.addWidget(self.scroll, 1)

    def fill(self, rows, today=None, tonight=()):
        today = today or date.today()
        due = sorted((r for r in rows if r["due_date"]), key=lambda r: r["due_date"])
        start = sorted((r for r in rows if r["start_date"] and not r["due_date"]
                        and r["start_date"] >= today.isoformat()), key=lambda r: r["start_date"])
        undated = sum(1 for r in rows if not r["due_date"] and not r["start_date"])

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(2)

        def section(text):
            lb = QLabel(text)
            lb.setStyleSheet("color:%s; padding:8px 4px 2px 4px;" % theme.TEXT_DIM)
            lay.addWidget(lb)

        def add(r, badge, color, parts, show_ago=True):
            if show_ago:
                _n, text, c = ago(r["activity"], today)
                parts = parts + ["<span style='color:%s'>%s</span>" % (c, text)]
            w = ScheduleRow(r, badge, color, "  ·  ".join(parts))
            w.clicked.connect(self.opened)
            lay.addWidget(w)

        def status(r):
            return [] if r["status"] == STATUSES[0] else [escape(r["status"])]

        def link(text, signal, tip):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("QPushButton { text-align:left; border:none; background:transparent; color:%s; padding:8px 4px 2px 4px; }"
                            "QPushButton:hover { color:%s; }" % (theme.TEXT_DIM, theme.ACCENT))
            b.clicked.connect(signal)
            lay.addWidget(b)

        # 오늘 밤 시간표
        if tonight:
            link("오늘 밤  ⤢ 시간표", self.timetableRequested, "주간 시간표 열기")
            for t, r in tonight:
                w = ScheduleRow({"uuid": r["idea_uuid"], "title": r["title"], "importance": r["importance"],
                                 "urgency": r["urgency"], "next_step": r["next_step"], "status": r["status"]},
                                t, theme.QUAD[2], "")
                w.clicked.connect(self.opened)
                lay.addWidget(w)

        # 진행 중 (최대 ACTIVE_LIMIT 개): 지금 손대고 있는 것과 그 다음 한 걸음
        active = sorted((r for r in rows if r["status"] == ACTIVE), key=lambda r: r["activity"])
        over = len(active) > ACTIVE_LIMIT
        lb = QLabel("진행 중  %d / %d" % (len(active), ACTIVE_LIMIT) +
                    ("  — 너무 많아요! 하나를 완료·보류로" if over else ""))
        lb.setWordWrap(True)
        lb.setStyleSheet("color:%s; font-weight:bold; padding:4px 4px 2px 4px;"
                         % (theme.DANGER if over else theme.ACCENT))
        lay.addWidget(lb)
        if not active:
            e = QLabel("진행 중인 아이디어가 없어요. 하나를 골라 상태를 '진행 중'으로 바꾸고 다음 한 걸음을 적어 보세요.")
            e.setWordWrap(True)
            e.setStyleSheet("color:%s; padding:2px 4px 6px 4px;" % theme.TEXT_DIM)
            lay.addWidget(e)
        for r in active:
            _n, text, c = ago(r["activity"], today)
            w = ScheduleRow(r, "", theme.ACCENT, "<span style='color:%s'>%s</span>" % (c, text))
            w.clicked.connect(self.opened)
            lay.addWidget(w)

        if due:
            section("목표일")
            for r in due:
                b, c = dday(r["due_date"], today)
                add(r, b, c, ["목표 " + r["due_date"][5:].replace("-", "/")] + status(r))
        if start:
            section("시작 예정")
            for r in start:
                b, _c = dday(r["start_date"], today)
                add(r, b, theme.QUAD[2], ["시작 " + r["start_date"][5:].replace("-", "/")] + status(r))
        if not due and not start:
            empty = QLabel("날짜를 정한 아이디어가 없어요.\n아이디어 화면에서 시작일·목표일을 넣으면 여기 보여요.")
            empty.setWordWrap(True)
            empty.setStyleSheet("color:%s; padding:8px 4px;" % theme.TEXT_DIM)
            lay.addWidget(empty)
        # 오래 손 안 댄 것: 일주일 넘게 안 건드린 아이디어 (보류는 일부러 쉬는 거라 뺌)
        stale = sorted((r for r in rows if r["status"] != "보류" and ago(r["activity"], today)[0] >= STALE_DAYS),
                       key=lambda r: r["activity"])
        if stale:
            link("오래 손 안 댄 것  ⤢ 주간 점검", self.reviewRequested, "멈춘 아이디어를 계속 / 보류 / 버리기로 정리")
            for r in stale[:8]:
                n, _t, c = ago(r["activity"], today)
                last = datetime.fromtimestamp(r["activity"] / 1000).strftime("%m/%d")
                add(r, "%d일째" % n, c, ["마지막 " + last] + status(r), show_ago=False)
            if len(stale) > 8:
                lb = QLabel("… 외 %d개" % (len(stale) - 8))
                lb.setStyleSheet("color:%s; padding:2px 8px;" % theme.TEXT_OFF)
                lay.addWidget(lb)
        if undated:
            lb = QLabel("날짜 없는 아이디어 %d개" % undated)
            lb.setStyleSheet("color:%s; padding:10px 4px 0 4px;" % theme.TEXT_OFF)
            lay.addWidget(lb)
        lay.addStretch(1)
        self.scroll.setWidget(body)


# ---------------------------------------------------------------- 할일 (일정 보드 아래)

class TodoRow(QFrame):
    """할일 한 줄: 끝냄 체크 · 포스트잇 색 · 글 · 기한."""

    def __init__(self, row, on_toggle, parent=None):
        super().__init__(parent)
        self.setObjectName("trow")
        self.setStyleSheet("#trow { border-radius:6px; } #trow:hover { background:%s; }" % theme.ITEM_HOVER)
        box = QCheckBox()
        box.setChecked(bool(row["done"]))
        box.setToolTip("끝냄")
        box.toggled.connect(lambda on: on_toggle(row["uuid"], on))
        chip = QLabel()
        chip.setFixedSize(12, 12)
        chip.setStyleSheet("background:%s; border-radius:2px;" % PAPER.get(row["color"], PAPER["yellow"]))
        first = (row["text"] or "(빈 할일)").splitlines()[0]
        self.text = QLabel()
        self.text.setMinimumWidth(10)
        self._full = first
        self.text.setToolTip(row["text"] + ("\n💡 " + row["idea_title"] if row["idea_title"] else ""))
        if row["done"]:
            self.text.setStyleSheet("color:%s; text-decoration: line-through;" % theme.TEXT_DIM)
        label, col = todo_dday(row["due_date"])
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 3, 6, 3)
        lay.setSpacing(6)
        lay.addWidget(box)
        lay.addWidget(chip)
        lay.addWidget(self.text, 1)
        if label and not row["done"]:
            d = QLabel(label)
            d.setStyleSheet("color:%s; font-weight:bold;" % (theme.DANGER if col == "#c0392b" else
                                                              theme.QUAD[3] if col == "#a15c00" else theme.TEXT_DIM))
            lay.addWidget(d)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        fm = self.text.fontMetrics()
        self.text.setText(fm.elidedText(self._full, Qt.ElideRight, max(20, self.text.width())))


class TodoPanel(QFrame):
    """일정 보드 아래 '할일' 칸. 제목을 누르거나 칸을 더블클릭하면 포스트잇 창."""
    openRequested = Signal()
    toggled = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("todos")
        self.setStyleSheet("#todos { background:%s; border:1px solid %s; border-radius:10px; }"
                           % (theme.SIDEBAR, theme.BORDER))
        self.setToolTip("더블클릭하면 포스트잇 창이 열려요")
        head = QPushButton("할일   ⤢ 포스트잇")
        head.setToolTip("할일을 포스트잇 벽으로 크게 보기")
        head.setCursor(Qt.PointingHandCursor)
        f = head.font()
        f.setPointSize(12)
        f.setBold(True)
        head.setFont(f)
        head.setStyleSheet("QPushButton { text-align:left; border:none; background:transparent; padding:2px 4px; }"
                           "QPushButton:hover { color:%s; background:%s; border-radius:5px; }"
                           % (theme.ACCENT, theme.ITEM_HOVER))
        head.clicked.connect(self.openRequested)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background:transparent; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 6, 8)
        lay.setSpacing(6)
        lay.addWidget(head)
        lay.addWidget(self.scroll, 1)

    def mouseDoubleClickEvent(self, ev):
        self.openRequested.emit()

    def fill(self, rows):
        open_rows = sorted((r for r in rows if not r["done"]), key=lambda r: (r["due_date"] or "9999", r["created_at"]))
        done_n = sum(1 for r in rows if r["done"])
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(1)
        for r in open_rows:
            lay.addWidget(TodoRow(r, lambda tid, on: self.toggled.emit(tid, on)))
        if not open_rows:
            empty = QLabel("할일이 없어요.\n더블클릭해서 포스트잇을 붙여보세요." if not done_n else "다 끝냈어요 👏")
            empty.setWordWrap(True)
            empty.setStyleSheet("color:%s; padding:8px 4px;" % theme.TEXT_DIM)
            lay.addWidget(empty)
        if done_n:
            lb = QLabel("끝낸 것 %d개" % done_n)
            lb.setStyleSheet("color:%s; padding:8px 4px 0 4px;" % theme.TEXT_OFF)
            lay.addWidget(lb)
        lay.addStretch(1)
        self.scroll.setWidget(body)


class DashboardPage(QWidget):
    reviewRequested = Signal()
    timetableRequested = Signal()
    opened = Signal(str)
    changed = Signal(str)
    ganttRequested = Signal()
    todosRequested = Signal()
    todoChanged = Signal()

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        title = QLabel("대시보드")
        f = title.font()
        f.setPointSize(18)
        f.setBold(True)
        title.setFont(f)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color:%s;" % theme.TEXT_DIM)
        self.chart = MatrixChart()
        self.chart.opened.connect(self.opened)
        self.chart.moved.connect(self._moved)
        self.schedule = SchedulePanel()
        self.schedule.opened.connect(self.opened)
        self.schedule.expandRequested.connect(self.ganttRequested)
        self.schedule.reviewRequested.connect(self.reviewRequested)
        self.schedule.timetableRequested.connect(self.timetableRequested)
        # 금요일 밤 알림 줄
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        self.banner.setStyleSheet("#banner { background:%s; border:1px solid %s; border-radius:10px; }"
                                  % (theme.PANEL, theme.QUAD[3]))
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(14, 8, 10, 8)
        self.banner_text = QLabel()
        go = QPushButton("주간 점검 하기")
        go.clicked.connect(self.reviewRequested)
        bl.addWidget(self.banner_text, 1)
        bl.addWidget(go)
        self.banner.hide()
        self.todos = TodoPanel()
        self.todos.openRequested.connect(self.todosRequested)
        self.todos.toggled.connect(self._todo_toggled)
        side = QWidget()
        side.setFixedWidth(260)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(10)
        sl.addWidget(self.schedule, 3)
        sl.addWidget(self.todos, 2)

        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(self.chart, 1)
        row.addWidget(side)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 20, 20, 16)
        lay.setSpacing(6)
        lay.addWidget(title)
        lay.addWidget(self.note)
        lay.addWidget(self.banner)
        lay.addSpacing(6)
        lay.addLayout(row, 1)

    def refresh(self):
        rows = [r for r in self.store.ideas() if r["status"] != "완료"]
        # 같은 칸 안에서는 목표일 빠른 순, 보류는 뒤로
        rows.sort(key=lambda r: (r["status"] == "보류", r["due_date"] or "9999", -r["activity"]))
        self.chart.set_rows(rows)
        self.schedule.fill(rows, tonight=weekly_tonight(self.store))
        self.todos.fill(self.store.todos())
        self.note.setText("아이디어 %d개 (완료 제외) · 칩을 누르면 열리고, 끌어서 옮기면 중요도·긴급도가 바뀌어요. "
                          "가운데 선이 3(보통), %d 이상이 '높음'." % (len(rows), HIGH))

    def set_review_banner(self, show, n):
        self.banner_text.setText("🗓 금요일 밤이에요. 멈춘 아이디어 %d개를 계속 / 보류 / 버리기로 정리할까요?" % n
                                 if n else "🗓 금요일 밤이에요. 이번 주 멈춘 아이디어는 없어요. 진행 중인 것만 훑어볼까요?")
        self.banner.setVisible(show)

    def _todo_toggled(self, tid, done):
        self.store.update_todo(tid, done=1 if done else 0)
        # 체크 신호 안에서 줄을 지우지 않게 다음 차례에 다시 그림
        QTimer.singleShot(0, lambda: (self.todos.fill(self.store.todos()), self.todoChanged.emit()))

    def _moved(self, uid, imp, urg):
        self.store.update(uid, importance=imp, urgency=urg)
        self.refresh()
        self.changed.emit(uid)

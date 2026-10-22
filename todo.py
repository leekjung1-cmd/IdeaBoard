"""할일 창: 코르크 벽에 포스트잇처럼 붙여 두고 한눈에 보기.

끌기 = 자리 옮기기, 오른쪽 위 동그라미 = 끝냄, 더블클릭 = 고치기, 우클릭 = 색·끝냄·아이디어 열기·삭제.
'가지런히 정리' = 기한 빠른 순으로 줄 맞춰 붙이기.
"""
import random
import zlib
from datetime import date, datetime, timedelta

from PySide6.QtCore import QPointF, QRectF, Qt, QTime, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF, QShortcut, QTextOption
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGraphicsDropShadowEffect,
    QGraphicsObject, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QSlider, QTableWidget, QTableWidgetItem, QTimeEdit, QVBoxLayout, QWidget,
)

import icons
import theme
from store import REMIND_PRESETS, TODO_COLORS
from widgets import DateField

NOTE_W, NOTE_H = 200, 180
GAP_X, GAP_Y = 36, 40
MARGIN = 40
PAPER = {"yellow": "#f1df8f", "pink": "#eebcc8", "green": "#c3dfb6", "blue": "#b9d3ea", "orange": "#f0c99e", "purple": "#d4c8ec"}
NAMES = {"yellow": "노랑", "pink": "분홍", "green": "초록", "blue": "파랑", "orange": "주황", "purple": "보라"}
INK = QColor("#2b2b2b")


def dday(due):
    if not due:
        return None, None
    n = (date.fromisoformat(due) - date.today()).days
    if n < 0:
        return "%d일 지남" % -n, "#c0392b"
    if n == 0:
        return "오늘까지", "#c0392b"
    return "D-%d" % n, ("#a15c00" if n <= 3 else "#555555")


def remind_text(row):
    """'알림 10/22 20:00 · 집에 가면' (없으면 '')"""
    at = row["remind_at"] if "remind_at" in row.keys() else None
    if not at:
        return ""
    d, t = at.split("T")
    label = row["remind_label"] if "remind_label" in row.keys() else ""
    return "알림 %s %s%s" % (d[5:].replace("-", "/"), t, "  ·  " + label if label else "")


def next_at(hhmm):
    """그 시각이 오늘 아직 안 지났으면 오늘, 지났으면 내일 (date, QTime)."""
    h, m = map(int, hhmm.split(":"))
    now = datetime.now()
    d = date.today() if (h, m) > (now.hour, now.minute) else date.today() + timedelta(days=1)
    return d, QTime(h, m)


class PresetDialog(QDialog):
    """알림 시간대 고치기: 이름 + 시각."""

    def __init__(self, presets, parent=None):
        super().__init__(parent)
        self.setWindowTitle("알림 시간대")
        self.setMinimumSize(360, 320)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["이름 (예: 집에 가면)", "시각 (예: 20:00)"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        for name, hhmm in presets:
            self._add(name, hhmm)
        add = QPushButton("＋ 추가")
        add.clicked.connect(lambda: self._add("", "09:00"))
        rm = QPushButton("고른 줄 지우기")
        rm.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()) if self.table.currentRow() >= 0 else None)
        row = QHBoxLayout()
        row.addWidget(add)
        row.addWidget(rm)
        row.addStretch(1)
        buttons = QDialogButtonBox()
        buttons.addButton("저장", QDialogButtonBox.AcceptRole)
        buttons.addButton("취소", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("할일 알림에서 고를 시간대예요. 폰 설정에서도 따로 정할 수 있어요."))
        lay.addWidget(self.table, 1)
        lay.addLayout(row)
        lay.addWidget(buttons)

    def _add(self, name, hhmm):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(name))
        self.table.setItem(r, 1, QTableWidgetItem(hhmm))

    def values(self):
        out = []
        for r in range(self.table.rowCount()):
            name = (self.table.item(r, 0).text() if self.table.item(r, 0) else "").strip()
            t = QTime.fromString((self.table.item(r, 1).text() if self.table.item(r, 1) else "").strip(), "H:mm")
            if name and t.isValid():
                out.append((name, t.toString("HH:mm")))
        return out


def wall_tile():
    """벽 바탕: 테마 바탕색 위 옅은 점 격자 (한 번 만들어 반복)."""
    pm = QPixmap(24, 24)
    pm.fill(QColor(theme.WINDOW))
    p = QPainter(pm)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(theme.BORDER))
    p.drawRect(QRectF(11, 11, 1.5, 1.5))
    p.end()
    return pm


class NoteItem(QGraphicsObject):
    def __init__(self, row, board):
        super().__init__()
        self.row = row
        self.board = board
        self.tid = row["uuid"]
        self.done = bool(row["done"])
        self.setFlags(QGraphicsObject.ItemIsMovable | QGraphicsObject.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.OpenHandCursor)
        self.setOpacity(0.6 if self.done else 1.0)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(10)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 90 if theme.DARK else 30))
        self.setGraphicsEffect(shadow)
        self._press_pos = None

    def boundingRect(self):
        return QRectF(-4, -14, NOTE_W + 8, NOTE_H + 18)

    def check_rect(self):
        return QRectF(NOTE_W - 30, 10, 20, 20)

    def paint(self, p, _opt, _w):
        p.setRenderHint(QPainter.Antialiasing)
        base = QColor(PAPER.get(self.row["color"], PAPER["yellow"]))
        p.setPen(QPen(base.darker(115), 1) if not self.isSelected() else QPen(QColor(theme.ACCENT), 2.5))
        p.setBrush(base)
        p.drawRoundedRect(QRectF(0, 0, NOTE_W, NOTE_H), theme.r(6), theme.r(6))

        # 끝냄 동그라미
        cr = self.check_rect()
        p.setPen(QPen(INK, 1.6))
        p.setBrush(INK if self.done else Qt.NoBrush)
        p.drawEllipse(cr)
        if self.done:
            p.setPen(QPen(QColor(base), 2.2))
            p.drawPolyline(QPolygonF([QPointF(cr.left() + 5, cr.center().y()), QPointF(cr.center().x() - 1, cr.bottom() - 5),
                                      QPointF(cr.right() - 4, cr.top() + 5)]))

        # 글
        f = QFont(p.font())
        f.setPointSizeF(11)
        f.setStrikeOut(self.done)
        p.setFont(f)
        p.setPen(INK)
        opt = QTextOption()
        opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        p.save()
        rt = remind_text(self.row)
        body = QRectF(14, 14, NOTE_W - 50, NOTE_H - (76 if rt else 58))      # 오른쪽 위 동그라미와 안 겹치게
        p.setClipRect(body)
        p.drawText(body.adjusted(0, 0, 0, 200), self.row["text"] or "(빈 할일)", opt)
        p.restore()

        # 아래: 기한 · 관련 아이디어
        small = QFont(p.font())
        small.setPointSizeF(9)
        small.setStrikeOut(False)
        p.setFont(small)
        label, col = dday(self.row["due_date"])
        y = NOTE_H - 40
        if rt:
            p.setPen(QColor("#1f5fbf"))
            p.drawText(QRectF(14, y - 18, NOTE_W - 28, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(rt, Qt.ElideRight, NOTE_W - 28))
        if label:
            p.setPen(QColor(col))
            f2 = QFont(small)
            f2.setBold(True)
            p.setFont(f2)
            p.drawText(QRectF(14, y, NOTE_W - 28, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       "%s  ·  %s" % (label, self.row["due_date"][5:].replace("-", "/")))
            p.setFont(small)
        if self.row["idea_title"]:
            p.setPen(QColor("#5a5a5a"))
            fm = p.fontMetrics()
            p.drawText(QRectF(14, y + 18, NOTE_W - 36, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText(self.row["idea_title"], Qt.ElideRight, NOTE_W - 36))

    # ---------- 마우스 ----------
    def hoverEnterEvent(self, ev):
        self.setZValue(10)
        super().hoverEnterEvent(ev)

    def hoverLeaveEvent(self, ev):
        self.setZValue(0)
        super().hoverLeaveEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.check_rect().adjusted(-4, -4, 4, 4).contains(ev.pos()):
            self.board.toggle_done(self.tid, not self.done)
            ev.accept()
            return
        self._press_pos = QPointF(self.pos())
        self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        self.setCursor(Qt.OpenHandCursor)
        if self._press_pos is not None and (self.pos() - self._press_pos).manhattanLength() > 2:
            self.board.save_positions([self])
        self._press_pos = None

    def mouseDoubleClickEvent(self, ev):
        self.board.edit(self.tid)

    def contextMenuEvent(self, ev):
        self.board.note_menu(self.tid, ev.screenPos())


class TodoDialog(QDialog):
    """새 할일 / 고치기."""
    presets = list(REMIND_PRESETS)      # 알림 시간대 [(이름, 'HH:MM')] — 본 창이 설정에서 채움
    save_presets = None                 # 시간대를 고쳤을 때 저장할 함수

    def __init__(self, ideas, row=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("할일 고치기" if row else "새 할일")
        self.setMinimumWidth(420)
        self.text = QPlainTextEdit(row["text"] if row else "")
        self.text.setPlaceholderText("할 일을 적어요 (여러 줄 가능)")
        self.text.setFixedHeight(110)
        self.color = row["color"] if row else "yellow"
        colors = QHBoxLayout()
        group = QButtonGroup(self)
        for c in TODO_COLORS:
            b = QPushButton()
            b.setCheckable(True)
            b.setChecked(c == self.color)
            b.setFixedSize(30, 30)
            b.setToolTip(NAMES[c])
            b.setStyleSheet("QPushButton { background:%s; border:2px solid %s; border-radius:15px; }"
                            "QPushButton:checked { border:3px solid %s; }" % (PAPER[c], theme.BORDER, theme.TEXT))
            b.clicked.connect(lambda _c=False, c=c: setattr(self, "color", c))
            group.addButton(b)
            colors.addWidget(b)
        colors.addStretch(1)
        self.due = DateField()
        self.due.setValue(row["due_date"] if row else None)
        self.idea = QComboBox()
        self.idea.addItem("(없음)", None)
        for r in ideas:
            self.idea.addItem(r["title"] or "(제목 없음)", r["uuid"])
        if row and row["idea_uuid"]:
            self.idea.setCurrentIndex(max(0, self.idea.findData(row["idea_uuid"])))

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow("할 일", self.text)
        form.addRow("색", colors)
        form.addRow("기한", self.due)
        form.addRow("관련 아이디어", self.idea)

        # 알림: 없음 / 시간대(집에 가면 …) / 직접 정하기 → 그 시각에 폰이 알려줌
        self.remind = QComboBox()
        self.remind_date = DateField()
        self.remind_time = QTimeEdit()
        self.remind_time.setDisplayFormat("HH:mm")
        self.remind_time.setButtonSymbols(QTimeEdit.NoButtons)
        edit_presets = QPushButton("시간대 고치기…")
        edit_presets.setFlat(True)
        edit_presets.setStyleSheet("color:%s;" % theme.ACCENT)
        edit_presets.clicked.connect(self._edit_presets)
        self._fill_remind()
        at = row["remind_at"] if row and "remind_at" in row.keys() else None
        label = (row["remind_label"] if row and "remind_label" in row.keys() else "") or ""
        if at:
            d, t = at.split("T")
            self.remind_date.setValue(d)
            self.remind_time.setTime(QTime.fromString(t, "HH:mm"))
            i = self.remind.findData(label) if label else -1
            self.remind.setCurrentIndex(i if i >= 0 else self.remind.count() - 1)
        self.remind.currentIndexChanged.connect(self._remind_picked)
        self.remind_when = QWidget()
        wl = QHBoxLayout(self.remind_when)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(self.remind_date)
        wl.addWidget(self.remind_time)
        wl.addStretch(1)
        rrow = QHBoxLayout()
        rrow.addWidget(self.remind, 1)
        rrow.addWidget(edit_presets)
        form.addRow("알림", rrow)
        form.addRow("", self.remind_when)
        self.remind_when.setVisible(bool(at))
        buttons = QDialogButtonBox()
        self.ok = buttons.addButton("저장" if row else "붙이기", QDialogButtonBox.AcceptRole)
        buttons.addButton("취소", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.text.textChanged.connect(lambda: self.ok.setEnabled(bool(self.text.toPlainText().strip())))
        self.ok.setEnabled(bool(self.text.toPlainText().strip()))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.addLayout(form)
        lay.addWidget(buttons)
        self.text.setFocus()

    def _fill_remind(self):
        self.remind.blockSignals(True)
        self.remind.clear()
        self.remind.addItem("없음", None)
        for name, hhmm in self.presets:
            self.remind.addItem("%s  (%s)" % (name, hhmm), name)
        self.remind.addItem("시간 직접 정하기", "")
        self.remind.blockSignals(False)

    def _remind_picked(self, _i):
        key = self.remind.currentData()
        self.remind_when.setVisible(key is not None)
        if key:             # 시간대: 그 시각이 오늘 지났으면 내일
            d, t = next_at(dict(self.presets)[key])
            self.remind_date.setValue(d.isoformat())
            self.remind_time.setTime(t)
        elif key == "" and not self.remind_date.value():     # 직접: 기본은 한 시간 뒤
            n = datetime.now() + timedelta(hours=1)
            self.remind_date.setValue(n.date().isoformat())
            self.remind_time.setTime(QTime(n.hour, 0))

    def _edit_presets(self):
        dlg = PresetDialog(self.presets, self)
        if dlg.exec() != QDialog.Accepted:
            return
        TodoDialog.presets = dlg.values()
        if TodoDialog.save_presets:
            TodoDialog.save_presets(TodoDialog.presets)
        cur = self.remind.currentData()
        self._fill_remind()
        i = self.remind.findData(cur)
        self.remind.setCurrentIndex(i if i >= 0 else 0)

    def values(self):
        key = self.remind.currentData()
        at = None
        if key is not None:
            at = "%sT%s" % (self.remind_date.value() or date.today().isoformat(), self.remind_time.time().toString("HH:mm"))
        label = key or ""
        if label and dict(self.presets).get(label) != self.remind_time.time().toString("HH:mm"):
            label = ""          # 시각을 손으로 바꿨으면 시간대 이름은 안 붙임
        return dict(text=self.text.toPlainText().strip(), color=self.color, due_date=self.due.value(),
                    idea_uuid=self.idea.currentData(), remind_at=at, remind_label=label)


class WallView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QBrush(wall_tile()))
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setStyleSheet("QGraphicsView { border:none; }")

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.ControlModifier:        # Ctrl+휠 = 확대·축소
            f = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
            s = self.transform().m11() * f
            if 0.4 <= s <= 2.0:
                self.scale(f, f)
            return
        super().wheelEvent(ev)


class TodoWindow(QDialog):
    changed = Signal()              # 할일이 바뀜 (왼쪽 목록 숫자 새로)
    openIdea = Signal(str)

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.setWindowTitle("할일 — 아이디어 보드")
        self.setWindowFlags(Qt.Window | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.resize(1100, 720)

        add = QPushButton(" 새 할일")
        add.setIcon(icons.icon("plus"))
        add.setStyleSheet("QPushButton { font-weight:bold; }")
        add.setToolTip("Ctrl+N")
        add.clicked.connect(self.new)
        tidy = QPushButton("가지런히 정리")
        tidy.setToolTip("기한 빠른 순으로 줄 맞춰 붙이기 (끝낸 것은 뒤로)")
        tidy.clicked.connect(self.tidy)
        self.hide_done = QCheckBox("끝낸 것 숨기기")
        self.hide_done.toggled.connect(self.refresh)
        self.count = QLabel()
        self.count.setStyleSheet("color:%s;" % theme.TEXT_DIM)
        # 투명도·항상 위: 다른 창 위에 반투명하게 띄워 두고 보기
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(30, 100)
        self.opacity.setValue(100)
        self.opacity.setFixedWidth(110)
        self.opacity.setToolTip("창 투명도")
        self.opacity_label = QLabel("100%")
        self.opacity_label.setFixedWidth(38)
        self.opacity.valueChanged.connect(self._set_opacity)
        self.on_top = QCheckBox("항상 위")
        self.on_top.setToolTip("다른 프로그램 위에 늘 떠 있기")
        self.on_top.toggled.connect(self._set_on_top)
        hint = QLabel("사용법")
        hint.setToolTip("끌어서 붙이기 · 오른쪽 위 동그라미 = 끝냄 · 더블클릭 고치기 · 우클릭 메뉴 · Del 삭제 · Ctrl+휠 확대 · Ctrl+N 새 할일")
        hint.setStyleSheet("color:%s;" % theme.TEXT_DIM)
        bar = QHBoxLayout()
        bar.addWidget(add)
        bar.addWidget(tidy)
        bar.addSpacing(10)
        bar.addWidget(self.hide_done)
        bar.addSpacing(10)
        bar.addWidget(self.count)
        bar.addStretch(1)
        op = QLabel("투명도")
        op.setStyleSheet("color:%s;" % theme.TEXT_DIM)
        bar.addWidget(op)
        bar.addWidget(self.opacity)
        bar.addWidget(self.opacity_label)
        bar.addWidget(self.on_top)
        bar.addSpacing(12)
        bar.addWidget(hint)

        self.scene = QGraphicsScene(self)
        self.view = WallView(self.scene)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        lay.addLayout(bar)
        lay.addWidget(self.view, 1)
        self.items = {}

        QShortcut(QKeySequence("Ctrl+N"), self, self.new)
        QShortcut(QKeySequence(Qt.Key_Delete), self, self.delete_selected)

    # ---------- 투명도·항상 위 ----------
    def _set_opacity(self, v):
        self.setWindowOpacity(v / 100.0)
        self.opacity_label.setText("%d%%" % v)

    def _set_on_top(self, on):
        if bool(self.windowFlags() & Qt.WindowStaysOnTopHint) == on:
            return
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)     # 창 속성을 바꾸면 잠깐 숨겨지므로 다시 보이기
        if was_visible:
            self.show()

    def view_prefs(self):
        return {"opacity": self.opacity.value(), "on_top": self.on_top.isChecked()}

    def apply_prefs(self, prefs):
        self.opacity.setValue(int(prefs.get("opacity", 100)))
        self.on_top.setChecked(bool(prefs.get("on_top", False)))

    # ---------- 그리기 ----------
    def refresh(self):
        rows = self.store.todos()
        self.scene.clear()
        self.items = {}
        unplaced = []
        for r in rows:
            if self.hide_done.isChecked() and r["done"]:
                continue
            item = NoteItem(r, self)
            self.scene.addItem(item)
            self.items[r["uuid"]] = item
            if r["x"] is None or r["y"] is None:
                unplaced.append(item)
            else:
                item.setPos(r["x"], r["y"])
        if unplaced:                            # 새로 온 것(폰·다른 곳)은 빈자리에
            for it in unplaced:
                it.setPos(self._free_slot(exclude=it))
            self.save_positions(unplaced, notify=False)
        self._fit_scene()
        open_n = sum(1 for r in rows if not r["done"])
        self.count.setText("할일 %d개 · 끝낸 것 %d개" % (open_n, len(rows) - open_n))
        if not rows:
            t = self.scene.addText("할일 없음")
            t.setDefaultTextColor(QColor(theme.TEXT_DIM))
            f = QFont(self.font())
            f.setPointSize(14)
            t.setFont(f)
            t.setPos(MARGIN, MARGIN)

    def _columns(self):
        w = self.view.viewport().width() / max(0.4, self.view.transform().m11())
        return max(1, int((w - MARGIN) // (NOTE_W + GAP_X)))

    def _slot(self, i):
        cols = self._columns()
        return QPointF(MARGIN + (i % cols) * (NOTE_W + GAP_X), MARGIN + (i // cols) * (NOTE_H + GAP_Y))

    def _free_slot(self, exclude=None):
        taken = [it.sceneBoundingRect() for it in self.items.values() if it is not exclude and it.row["x"] is not None]
        taken += [it.sceneBoundingRect() for it in self.items.values() if it is not exclude and it.pos() != QPointF(0, 0)]
        i = 0
        while True:
            pos = self._slot(i)
            rect = QRectF(pos, pos + QPointF(NOTE_W, NOTE_H))
            if not any(rect.intersects(t) for t in taken):
                return pos
            i += 1

    def _fit_scene(self):
        # 벽 크기 = 포스트잇이 있는 곳까지 (창보다 작으면 창 크기) → 필요할 때만 스크롤
        r = self.scene.itemsBoundingRect()
        vp = self.view.viewport().rect()
        k = max(0.4, self.view.transform().m11())
        self.scene.setSceneRect(QRectF(0, 0, max(r.right() + MARGIN, vp.width() / k - 2),
                                       max(r.bottom() + MARGIN, vp.height() / k - 2)))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._fit_scene()

    def showEvent(self, ev):
        super().showEvent(ev)
        self.refresh()

    # ---------- 동작 ----------
    def save_positions(self, items, notify=True):
        for it in items:
            self.store.update_todo(it.tid, x=round(it.pos().x(), 1), y=round(it.pos().y(), 1))
        self._fit_scene()
        if notify:
            self.changed.emit()

    def new(self):
        dlg = TodoDialog(self.store.ideas(), parent=self)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        self.store.add_todo(v.pop("text"), **v)     # 자리는 refresh 때 빈자리에
        self.refresh()
        self.changed.emit()

    def edit(self, tid):
        row = next((r for r in self.store.todos() if r["uuid"] == tid), None)
        if row is None:
            return
        dlg = TodoDialog(self.store.ideas(), row, self)
        if dlg.exec() == QDialog.Accepted:
            self.store.update_todo(tid, **dlg.values())
            self.refresh()
            self.changed.emit()

    def toggle_done(self, tid, done):
        self.store.update_todo(tid, done=1 if done else 0)
        self.refresh()
        self.changed.emit()

    def set_color(self, tid, color):
        self.store.update_todo(tid, color=color)
        self.refresh()
        self.changed.emit()

    def delete(self, tids):
        if not tids:
            return
        if QMessageBox.question(self, "할일 삭제", "포스트잇 %d개를 뗄까요?" % len(tids)) != QMessageBox.Yes:
            return
        for tid in tids:
            self.store.delete_todo(tid)
        self.refresh()
        self.changed.emit()

    def delete_selected(self):
        self.delete([it.tid for it in self.scene.selectedItems() if isinstance(it, NoteItem)])

    def note_menu(self, tid, screen_pos):
        it = self.items.get(tid)
        if it is None:
            return
        m = QMenu(self)
        m.addAction("고치기", lambda: self.edit(tid))
        m.addAction("다시 할 것으로" if it.done else "끝냄", lambda: self.toggle_done(tid, not it.done))
        colors = m.addMenu("색 바꾸기")
        for c in TODO_COLORS:
            a = colors.addAction(NAMES[c], lambda c=c: self.set_color(tid, c))
            a.setCheckable(True)
            a.setChecked(it.row["color"] == c)
        if it.row["idea_uuid"] and it.row["idea_title"]:
            m.addAction("💡 '%s' 열기" % it.row["idea_title"], lambda: self.openIdea.emit(it.row["idea_uuid"]))
        m.addSeparator()
        m.addAction("떼기 (삭제)", lambda: self.delete([tid]))
        m.exec(screen_pos)

    def tidy(self):
        order = sorted(self.items.values(), key=lambda it: (
            bool(it.row["done"]), it.row["due_date"] or "9999-99-99", it.row["created_at"]))
        for i, it in enumerate(order):
            it.setPos(self._slot(i))
        self.save_positions(order)

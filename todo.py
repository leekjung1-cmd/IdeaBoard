"""할일 창: 코르크 벽에 포스트잇처럼 붙여 두고 한눈에 보기.

끌기 = 자리 옮기기, 오른쪽 위 동그라미 = 끝냄, 더블클릭 = 고치기, 우클릭 = 색·끝냄·아이디어 열기·삭제.
'가지런히 정리' = 기한 빠른 순으로 줄 맞춰 붙이기.
"""
import random
import zlib
from datetime import date

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QKeySequence, QLinearGradient, QPainter, QPen, QPixmap, QPolygonF, QShortcut, QTextOption
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGraphicsDropShadowEffect,
    QGraphicsObject, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QMenu, QMessageBox, QPlainTextEdit,
    QPushButton, QVBoxLayout,
)

import theme
from store import TODO_COLORS
from widgets import DateField

NOTE_W, NOTE_H = 200, 180
GAP_X, GAP_Y = 36, 40
MARGIN = 40
PAPER = {"yellow": "#f7e27a", "pink": "#f5a9bc", "green": "#b0e3a6", "blue": "#a7cff3", "orange": "#f7c58a", "purple": "#cfbaf2"}
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


def wall_tile():
    """어두운 코르크 느낌 바탕 (한 번 만들어 반복)."""
    pm = QPixmap(240, 240)
    pm.fill(QColor("#3a3027"))
    p = QPainter(pm)
    rnd = random.Random(7)
    for _ in range(2600):
        c = QColor(rnd.choice(["#4a3d30", "#2f261e", "#45382b", "#524332", "#2a221b"]))
        c.setAlpha(rnd.randint(90, 200))
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        r = rnd.uniform(0.6, 1.8)
        p.drawEllipse(QPointF(rnd.uniform(0, 240), rnd.uniform(0, 240)), r, r)
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
        tilt = (zlib.crc32(self.tid.encode()) % 700) / 100.0 - 3.5     # 포스트잇마다 조금씩 다르게 기울기
        self.setTransformOriginPoint(NOTE_W / 2, NOTE_H / 2)
        self.setRotation(tilt * 0.8)
        self.setOpacity(0.72 if self.done else 1.0)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(18)
        shadow.setOffset(4, 7)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)
        self._press_pos = None

    def boundingRect(self):
        return QRectF(-4, -14, NOTE_W + 8, NOTE_H + 18)

    def check_rect(self):
        return QRectF(NOTE_W - 30, 10, 20, 20)

    def paint(self, p, _opt, _w):
        p.setRenderHint(QPainter.Antialiasing)
        base = QColor(PAPER.get(self.row["color"], PAPER["yellow"]))
        g = QLinearGradient(0, 0, 0, NOTE_H)
        g.setColorAt(0, base.lighter(108))
        g.setColorAt(1, base.darker(104))
        p.setPen(QPen(base.darker(125), 0.8) if not self.isSelected() else QPen(QColor(theme.ACCENT), 2.5))
        p.setBrush(QBrush(g))
        # 오른쪽 아래가 살짝 말린 종이
        paper = QPolygonF([QPointF(0, 0), QPointF(NOTE_W, 0), QPointF(NOTE_W, NOTE_H - 16),
                           QPointF(NOTE_W - 16, NOTE_H), QPointF(0, NOTE_H)])
        p.drawPolygon(paper)
        p.setPen(Qt.NoPen)
        p.setBrush(base.darker(118))
        p.drawPolygon(QPolygonF([QPointF(NOTE_W, NOTE_H - 16), QPointF(NOTE_W - 16, NOTE_H), QPointF(NOTE_W - 14, NOTE_H - 14)]))
        # 테이프
        p.setBrush(QColor(255, 255, 255, 105))
        p.drawRect(QRectF(NOTE_W / 2 - 34, -10, 68, 22))

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
        body = QRectF(14, 14, NOTE_W - 50, NOTE_H - 58)      # 오른쪽 위 동그라미와 안 겹치게
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
        if label:
            p.setPen(QColor(col))
            f2 = QFont(small)
            f2.setBold(True)
            p.setFont(f2)
            p.drawText(QRectF(14, y, NOTE_W - 28, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       "⏰ %s  (%s)" % (label, self.row["due_date"][5:].replace("-", "/")))
            p.setFont(small)
        if self.row["idea_title"]:
            p.setPen(QColor("#5a5a5a"))
            fm = p.fontMetrics()
            p.drawText(QRectF(14, y + 18, NOTE_W - 36, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       fm.elidedText("💡 " + self.row["idea_title"], Qt.ElideRight, NOTE_W - 36))

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

    def values(self):
        return dict(text=self.text.toPlainText().strip(), color=self.color, due_date=self.due.value(),
                    idea_uuid=self.idea.currentData())


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

        add = QPushButton("＋  새 할일")
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
        hint = QLabel("끌어서 붙이기 · ○ 끝냄 · 더블클릭 고치기 · 우클릭 메뉴 · Del 삭제 · Ctrl+휠 확대")
        hint.setStyleSheet("color:%s;" % theme.TEXT_DIM)
        bar = QHBoxLayout()
        bar.addWidget(add)
        bar.addWidget(tidy)
        bar.addSpacing(10)
        bar.addWidget(self.hide_done)
        bar.addSpacing(10)
        bar.addWidget(self.count)
        bar.addStretch(1)
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
            t = self.scene.addText("아직 할일이 없어요.\n＋ 새 할일로 첫 포스트잇을 붙여보세요.")
            t.setDefaultTextColor(QColor("#d8cbb8"))
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
        m.addAction("다시 할 것으로" if it.done else "끝냄 ✓", lambda: self.toggle_done(tid, not it.done))
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

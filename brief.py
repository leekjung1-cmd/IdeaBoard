"""기획서 탭: 아이디어마다 칸(제목 + 내용)을 자유롭게 채우고 고친다.

새 아이디어는 store.BRIEF_FIELDS 기본 칸(개발 의도 · 기능 · 플랫폼·기술)으로 시작하고,
칸 제목 고치기·칸 추가·순서 바꾸기·삭제, 체크해서 여러 칸 한꺼번에 삭제가 된다. 글은 쓰는 대로 알아서 저장.
"""
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

import theme
from store import BRIEF_FIELDS, LEGACY_BRIEF_FIELDS

HINTS = {key: hint for key, _label, hint in LEGACY_BRIEF_FIELDS + BRIEF_FIELDS}


class AutoText(QTextEdit):
    """글 길이에 맞춰 높이가 늘어나는 입력칸 (자체 스크롤 없음)."""

    def __init__(self, parent=None, min_lines=2):
        super().__init__(parent)
        self.min_lines = min_lines
        self.setAcceptRichText(False)
        self.setTabChangesFocus(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().documentLayout().documentSizeChanged.connect(self._fit)
        self._fit()

    def _fit(self, *_):
        extra = self.height() - self.viewport().height()
        lines = self.fontMetrics().lineSpacing()
        h = max(int(self.document().size().height()) + extra, lines * self.min_lines + extra + 8)
        if h != self.height():
            self.setFixedHeight(h)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._fit()

    def wheelEvent(self, ev):
        ev.ignore()     # 바깥 목록이 스크롤되게


class SectionWidget(QWidget):
    """칸 하나: 선택 체크 + ●/○ 표시 + 제목(바로 고칠 수 있음) + ⋯ 메뉴 + 내용."""
    edited = Signal(str)            # 칸 uuid
    action = Signal(str, str)       # 칸 uuid, 'up' | 'down' | 'delete' | 'add_below'
    selected = Signal()             # 선택 체크가 바뀜

    def __init__(self, row, first, last, parent=None):
        super().__init__(parent)
        self.sid = row["uuid"]
        self.pick = QCheckBox()
        self.pick.setToolTip("체크해서 여러 칸을 한꺼번에 삭제")
        self.pick.toggled.connect(lambda _on: self.selected.emit())
        self.mark = QLabel()
        self.mark.setFixedWidth(14)
        self.title = QLineEdit(row["title"])
        self.title.setPlaceholderText("칸 제목")
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        self.title.setStyleSheet(
            "QLineEdit { border:1px solid transparent; background:transparent; padding:1px 3px; }"
            "QLineEdit:hover { border-color:%s; } QLineEdit:focus { border-color:%s; background:%s; }"
            % (theme.BORDER, theme.ACCENT, theme.BASE))
        more = QToolButton()
        more.setText("⋯")
        more.setToolTip("칸 메뉴")
        more.setPopupMode(QToolButton.InstantPopup)
        more.setStyleSheet("QToolButton { padding:0 8px; color:%s; font-size:13pt; } QToolButton::menu-indicator { image:none; }"
                           % theme.TEXT_DIM)
        m = QMenu(more)
        up = m.addAction("위로", lambda: self.action.emit(self.sid, "up"))
        down = m.addAction("아래로", lambda: self.action.emit(self.sid, "down"))
        up.setEnabled(not first)
        down.setEnabled(not last)
        m.addAction("아래에 칸 추가", lambda: self.action.emit(self.sid, "add_below"))
        m.addSeparator()
        m.addAction("칸 삭제", lambda: self.action.emit(self.sid, "delete"))
        more.setMenu(m)

        self.text = AutoText()
        self.text.setPlainText(row["content"])
        self.text.setPlaceholderText(HINTS.get(row["key"], "내용"))

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(4)
        head.addWidget(self.pick)
        head.addWidget(self.mark)
        head.addWidget(self.title, 1)
        head.addWidget(more)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        lay.addLayout(head)
        lay.addWidget(self.text)

        self._update_mark()
        self.title.textEdited.connect(lambda _t: self.edited.emit(self.sid))
        self.text.textChanged.connect(self._text_changed)

    def _text_changed(self):
        self._update_mark()
        self.edited.emit(self.sid)

    def filled(self):
        return bool(self.text.toPlainText().strip())

    def _update_mark(self):
        c = theme.GOOD if self.filled() else theme.TEXT_OFF
        self.mark.setText("<span style='color:%s'>%s</span>" % (c, "●" if self.filled() else "○"))


class BriefView(QWidget):
    changed = Signal(str)       # 저장했음 (아이디어 uid)
    edited = Signal()           # 글자·칸 수가 바뀜 (진행도 표시용)

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.uid = None
        self.widgets = []
        self._dirty = set()

        # 위: 전체 선택 · 선택한 칸 삭제
        self.all_box = QCheckBox("전체 선택")
        self.all_box.setTristate(False)
        self.all_box.clicked.connect(self._select_all)
        self.del_btn = QPushButton("선택한 칸 삭제")
        self.del_btn.clicked.connect(self._delete_selected)
        bar = QHBoxLayout()
        bar.setContentsMargins(2, 10, 14, 0)
        bar.addWidget(self.all_box)
        bar.addSpacing(8)
        bar.addWidget(self.del_btn)
        bar.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(bar)
        lay.addWidget(self.scroll, 1)

        self._timer = QTimer(self, singleShot=True, interval=600)
        self._timer.timeout.connect(self.flush)

    # ---------- 읽기 ----------
    def load(self, uid, focus=None, keep_scroll=False):
        """uid 아이디어의 칸들을 새로 그림. focus = 제목 칸에 커서를 둘 칸 uuid."""
        self.flush()
        sb = self.scroll.verticalScrollBar()
        scroll = sb.value() if keep_scroll else 0
        self.uid = uid
        rows = self.store.sections(uid)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(2, 12, 14, 20)
        lay.setSpacing(14)
        self.widgets = []
        for i, r in enumerate(rows):
            w = SectionWidget(r, i == 0, i == len(rows) - 1)
            w.edited.connect(self._on_edit)
            w.action.connect(self._on_action)
            w.selected.connect(self._update_select_bar)
            self.widgets.append(w)
            lay.addWidget(w)
        if not rows:
            empty = QLabel("칸이 없어요. 아래 ＋ 칸 추가로 만들어요.")
            empty.setStyleSheet("color:%s; padding:10px 2px;" % theme.TEXT_DIM)
            lay.addWidget(empty)
        add = QPushButton("＋  칸 추가")
        add.setToolTip("제목과 내용을 직접 정하는 새 칸")
        add.setStyleSheet("QPushButton { border:1px dashed %s; background:transparent; padding:8px; color:%s; }"
                          "QPushButton:hover { border-color:%s; color:%s; }"
                          % (theme.BORDER, theme.TEXT_DIM, theme.ACCENT, theme.TEXT))
        add.clicked.connect(lambda: self._add(None))
        lay.addWidget(add)
        lay.addStretch(1)
        self.scroll.setWidget(body)       # 예전 body 는 알아서 지워짐
        QTimer.singleShot(0, lambda: sb.setValue(scroll))
        if focus:
            QTimer.singleShot(0, lambda: self._focus_title(focus))
        self._update_select_bar()
        self.edited.emit()

    def _focus_title(self, sid):
        # 그 사이 다시 그려졌을 수 있으니 지금 있는 위젯에서 찾음
        for w in self.widgets:
            if w.sid == sid:
                self.scroll.ensureWidgetVisible(w, 0, 60)
                w.title.setFocus()
                w.title.selectAll()

    def counts(self):
        """(채운 칸 수, 전체 칸 수)"""
        return sum(1 for w in self.widgets if w.filled()), len(self.widgets)

    def section_titles(self):
        """[(칸 uuid, 제목)] — 메모를 기획서로 보낼 때 씀."""
        self.flush()
        return [(r["uuid"], r["title"] or "(제목 없음)") for r in self.store.sections(self.uid)] if self.uid else []

    # ---------- 선택 삭제 ----------
    def picked(self):
        return [w for w in self.widgets if w.pick.isChecked()]

    def _update_select_bar(self):
        n, total = len(self.picked()), len(self.widgets)
        self.all_box.setEnabled(total > 0)
        self.all_box.blockSignals(True)
        self.all_box.setCheckState(Qt.Checked if total and n == total else
                                   Qt.PartiallyChecked if n else Qt.Unchecked)
        self.all_box.blockSignals(False)
        self.del_btn.setEnabled(n > 0)
        self.del_btn.setText("선택한 칸 삭제 (%d)" % n if n else "선택한 칸 삭제")

    def _select_all(self):
        on = len(self.picked()) < len(self.widgets)     # 하나라도 안 골랐으면 전부 고르기, 다 골랐으면 전부 풀기
        for w in self.widgets:
            w.pick.blockSignals(True)
            w.pick.setChecked(on)
            w.pick.blockSignals(False)
        self._update_select_bar()

    def _delete_selected(self):
        picked = self.picked()
        if not picked:
            return
        filled = sum(1 for w in picked if w.filled())
        msg = "칸 %d개를 지울까요?" % len(picked)
        if filled:
            msg += "\n(그중 %d개는 내용이 있어요)" % filled
        if QMessageBox.question(self, "칸 삭제", msg) != QMessageBox.Yes:
            return
        self.flush()
        self.store.delete_sections([w.sid for w in picked])
        self.load(self.uid, keep_scroll=True)
        self.changed.emit(self.uid)

    # ---------- 쓰기 ----------
    def _on_edit(self, sid):
        self._dirty.add(sid)
        self._timer.start()
        self.edited.emit()

    def flush(self):
        self._timer.stop()
        if not self.uid or not self._dirty:
            self._dirty.clear()
            return
        for w in self.widgets:
            if w.sid in self._dirty:
                self.store.update_section(w.sid, title=w.title.text().strip(), content=w.text.toPlainText().rstrip())
        self._dirty.clear()
        self.changed.emit(self.uid)

    def _add(self, after):
        self.flush()
        sid = self.store.add_section(self.uid, "", after=after)
        self.load(self.uid, focus=sid, keep_scroll=True)
        self.changed.emit(self.uid)

    def _on_action(self, sid, what):
        self.flush()
        if what == "add_below":
            self._add(sid)
            return
        if what == "delete":
            w = next(x for x in self.widgets if x.sid == sid)
            name = w.title.text().strip() or "(제목 없음)"
            if w.filled() and QMessageBox.question(
                    self, "칸 삭제", "'%s' 칸을 내용과 함께 삭제할까요?" % name) != QMessageBox.Yes:
                return
            self.store.delete_section(sid)
        elif what in ("up", "down"):
            self.store.move_section(sid, -1 if what == "up" else 1)
        self.load(self.uid, keep_scroll=True)
        self.changed.emit(self.uid)

    def reload(self):
        """밖에서(메모 보내기 등) 칸 내용이 바뀌었을 때."""
        if self.uid:
            self.load(self.uid, keep_scroll=True)

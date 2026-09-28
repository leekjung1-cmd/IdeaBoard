"""여러 창에서 같이 쓰는 작은 입력 부품."""
from PySide6.QtCore import QDate, QLocale, QPoint, Signal
from PySide6.QtWidgets import QCalendarWidget, QHBoxLayout, QMenu, QPushButton, QVBoxLayout, QWidget, QWidgetAction

import theme


class DateField(QPushButton):
    """비워둘 수 있는 날짜. 누르면 달력이 뜸."""
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = None
        self.setMinimumWidth(118)
        self.clicked.connect(self._pick)
        self._show()

    def value(self):
        return self._value

    def setValue(self, v):
        self._value = v or None
        self._show()

    def _show(self):
        self.setText(self._value or "날짜 없음")
        self.setStyleSheet("" if self._value else "color:%s;" % theme.TEXT_DIM)

    def _set(self, v):
        if v != self._value:
            self.setValue(v)
            self.changed.emit()

    def _pick(self):
        menu = QMenu(self)
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 4, 4, 4)
        cal = QCalendarWidget()
        cal.setLocale(QLocale(QLocale.Korean, QLocale.SouthKorea))
        cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        cal.setGridVisible(False)
        if self._value:
            cal.setSelectedDate(QDate.fromString(self._value, "yyyy-MM-dd"))
        lay.addWidget(cal)
        row = QHBoxLayout()
        today = QPushButton("오늘")
        clear = QPushButton("지우기")
        row.addWidget(today)
        row.addStretch(1)
        row.addWidget(clear)
        lay.addLayout(row)
        act = QWidgetAction(menu)
        act.setDefaultWidget(box)
        menu.addAction(act)

        def pick(d):
            self._set(d.toString("yyyy-MM-dd"))
            menu.close()

        cal.clicked.connect(pick)
        cal.activated.connect(pick)
        today.clicked.connect(lambda: pick(QDate.currentDate()))
        clear.clicked.connect(lambda: (self._set(None), menu.close()))
        menu.exec(self.mapToGlobal(QPoint(0, self.height())))

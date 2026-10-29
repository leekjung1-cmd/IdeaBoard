"""할일 알람: 정한 시각이 되면 PC에 팝업 (맨 위에 뜨고 소리).

팝업에서 끝냄 / 10분 뒤 / 30분 뒤 / 1시간 뒤 / ＋(누른 횟수만큼 시간 뒤) / 닫기.
같은 알람은 한 번만 뜸 (설정 alarm_fired 에 uuid → 울린 시각 기록). 폰도 같은 시각에 알람을 울림.
"""
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

import theme

FMT = "%Y-%m-%dT%H:%M"
SNOOZES = [("10분 뒤", 10), ("30분 뒤", 30), ("1시간 뒤", 60)]
PLUS_WAIT_MS = 1500         # ＋ 를 연달아 누르는 동안 기다렸다가 적용
LATE_LIMIT = timedelta(hours=12)     # 이보다 오래 지난 알람은 (PC를 꺼 뒀던 동안 등) 띄우지 않음


def after(minutes):
    """지금부터 minutes 분 뒤 'YYYY-MM-DDTHH:MM' (초가 있으면 다음 분으로 올림)."""
    now = datetime.now()
    t = now.replace(second=0, microsecond=0) + timedelta(minutes=minutes + (1 if now.second or now.microsecond else 0))
    return t.strftime(FMT)


def ring():
    try:
        import winsound
        winsound.PlaySound("SystemNotification", winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        QApplication.beep()


class PlusButton(QPushButton):
    """＋ : 누를 때마다 1시간씩 늘어남 (두 번 = 2시간 뒤, 세 번 = 3시간 뒤). picked(분)."""
    picked = Signal(int)

    def __init__(self, wait=True, parent=None):
        super().__init__("＋", parent)
        self.setToolTip("누른 횟수만큼 시간 뒤 (두 번 = 2시간, 세 번 = 3시간)")
        self.n = 0
        self.wait = wait            # True = 연달아 누르기가 끝나면 한 번에 알림 (팝업용)
        self._timer = QTimer(self, singleShot=True, interval=PLUS_WAIT_MS)
        self._timer.timeout.connect(lambda: self.picked.emit(self.n * 60))
        self.clicked.connect(self._click)

    def _click(self):
        self.n += 1
        self.setText("＋%d시간" % self.n)
        if self.wait:
            self._timer.start()
        else:
            self.picked.emit(self.n * 60)

    def reset(self):
        self.n = 0
        self._timer.stop()
        self.setText("＋")


class AlarmPopup(QDialog):
    """알람 팝업 하나 (할일 하나). acted(uuid, 동작, 분) — 동작 = done | snooze | close"""
    acted = Signal(str, str, int)

    def __init__(self, row, parent=None):
        super().__init__(parent)
        self.tid = row["uuid"]
        self.setWindowTitle("할일 알람")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMinimumWidth(440)
        head = QLabel("할일 알람" + ("  ·  " + row["remind_label"] if row["remind_label"] else "")
                      + "   " + row["remind_at"][11:])
        head.setStyleSheet("color:%s; font-weight:bold;" % theme.ACCENT)
        text = QLabel(row["text"] or "(빈 할일)")
        text.setWordWrap(True)
        f = text.font()
        f.setPointSize(15)
        f.setBold(True)
        text.setFont(f)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(10)
        lay.addWidget(head)
        lay.addWidget(text)
        if row["idea_title"]:
            sub = QLabel("아이디어: " + row["idea_title"])
            sub.setStyleSheet("color:%s;" % theme.TEXT_DIM)
            lay.addWidget(sub)
        lay.addSpacing(6)
        snooze = QHBoxLayout()
        snooze.setSpacing(6)
        for label, mins in SNOOZES:
            b = QPushButton(label)
            b.clicked.connect(lambda _c=False, m=mins: self._act("snooze", m))
            snooze.addWidget(b)
        plus = PlusButton(wait=True)
        plus.picked.connect(lambda m: self._act("snooze", m))
        snooze.addWidget(plus)
        lay.addLayout(snooze)
        bottom = QHBoxLayout()
        close = QPushButton("닫기")
        close.setToolTip("알람만 끄기 (할일은 그대로)")
        close.clicked.connect(lambda: self._act("close", 0))
        done = QPushButton("끝냄")
        done.setDefault(True)
        done.setStyleSheet("QPushButton { background:%s; color:%s; border:none; font-weight:bold; padding:7px 22px; }"
                           % (theme.ACCENT, theme.ON_ACCENT))
        done.clicked.connect(lambda: self._act("done", 0))
        bottom.addWidget(close)
        bottom.addStretch(1)
        bottom.addWidget(done)
        lay.addLayout(bottom)

    def _act(self, what, mins):
        self.acted.emit(self.tid, what, mins)
        self.close()

    def reject(self):           # Esc · 창 닫기 = 닫기
        self._act("close", 0)


class AlarmWatcher(QObject):
    """20초마다 알람 시각이 된 할일을 찾아 팝업. changed = 할일이 바뀜 (끝냄·미루기)."""
    changed = Signal()

    def __init__(self, store_, settings, save_settings, parent=None):
        super().__init__(parent)
        self.store = store_
        self.settings = settings
        self.save_settings = save_settings
        self.popups = {}
        self._timer = QTimer(self, interval=20_000)
        self._timer.timeout.connect(self.check)
        self._timer.start()
        QTimer.singleShot(3000, self.check)

    def check(self):
        now = datetime.now()
        fired = self.settings.setdefault("alarm_fired", {})
        for r in self.store.todos():
            at = r["remind_at"]
            if r["done"] or not at or fired.get(r["uuid"]) == at or r["uuid"] in self.popups:
                continue
            try:
                t = datetime.strptime(at, FMT)
            except ValueError:
                continue
            if t > now:
                continue
            fired[r["uuid"]] = at
            if now - t > LATE_LIMIT:
                continue
            self._show(r)
        live = {r["uuid"] for r in self.store.todos()}
        for k in [k for k in fired if k not in live]:      # 지운 할일 기록은 정리
            del fired[k]
        self.save_settings()

    def _show(self, row):
        p = AlarmPopup(row, self.parent())
        p.acted.connect(self._acted)
        p.destroyed.connect(lambda _o=None, tid=row["uuid"]: self.popups.pop(tid, None))
        self.popups[row["uuid"]] = p
        p.show()
        p.raise_()
        p.activateWindow()
        QApplication.alert(p)       # 작업 표시줄 깜빡
        ring()

    def _acted(self, tid, what, mins):
        if what == "done":
            self.store.update_todo(tid, done=1)
        elif what == "snooze":
            self.store.update_todo(tid, remind_at=after(mins), remind_label="")
        if what != "close":
            self.changed.emit()

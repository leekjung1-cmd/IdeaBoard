"""'폰 연결' 창: 폰 앱에 넣을 6자리 코드, 연결된 폰, 마지막으로 맞춘 시각."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

import theme
from sync import local_ip


class PhoneDialog(QDialog):
    def __init__(self, server, parent=None):
        super().__init__(parent)
        self.server = server
        self.setWindowTitle("폰 연결 (와이파이 동기화)")
        self.setMinimumWidth(460)

        how = QLabel("폰의 '아이디어 보드' 앱 → 설정 → PC 찾기 → 아래 코드를 입력하세요.\n"
                     "폰과 PC가 같은 와이파이에 있고, 이 프로그램이 켜져 있어야 맞춰져요.")
        how.setWordWrap(True)
        how.setStyleSheet("color:%s;" % theme.TEXT_DIM)
        self.code = QLabel()
        self.code.setAlignment(Qt.AlignCenter)
        self.code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.code.setStyleSheet("font-size:30pt; font-weight:bold; letter-spacing:6px; color:%s;"
                                "background:%s; border:1px solid %s; border-radius:10px; padding:10px;"
                                % (theme.TEXT, theme.BASE, theme.BORDER))
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)

        reset = QPushButton("코드 새로 만들기 (연결된 폰 모두 끊기)")
        reset.clicked.connect(self._reset)
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addWidget(reset)
        row.addStretch(1)
        row.addWidget(close)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 16)
        lay.setSpacing(12)
        lay.addWidget(how)
        lay.addWidget(self.code)
        lay.addWidget(self.info)
        lay.addLayout(row)

        self._timer = QTimer(self, interval=1000)
        self._timer.timeout.connect(self._show)
        self._timer.start()
        self._show()

    def _show(self):
        s = self.server
        self.code.setText(s.code)
        lines = []
        if s.error:
            lines.append("<span style='color:%s'>⚠ %s</span>" % (theme.DANGER, s.error))
        else:
            lines.append("이 PC: <b>%s</b> (%s)" % (s.config["name"], local_ip()))
        devs = s.devices()
        if devs:
            lines.append("연결된 폰: " + ", ".join("%s (%s 연결)" % (d.get("device", "폰"), d.get("paired", "")) for d in devs))
        else:
            lines.append("<span style='color:%s'>아직 연결된 폰이 없어요.</span>" % theme.TEXT_DIM)
        if s.last:
            lines.append("마지막으로 맞춘 때: %s · %s" % (s.last["at"], s.last["device"]))
        lines.append("<span style='color:%s'>처음 연결할 때 윈도우 방화벽 창이 뜨면 '허용'을 눌러 주세요.</span>"
                     % theme.TEXT_DIM)
        self.info.setText("<br>".join(lines))

    def _reset(self):
        if QMessageBox.question(self, "코드 새로 만들기",
                                "새 코드를 만들면 지금 연결된 폰은 모두 끊겨요.\n폰에서 새 코드로 다시 연결해야 해요. 만들까요?") \
                == QMessageBox.Yes:
            self.server.reset_code()
            self._show()

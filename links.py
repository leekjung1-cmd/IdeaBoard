"""아이디어마다 클로드 세션(또는 아무 링크) 바로가기.

클로드 앱 세션 링크: claude://claude.ai/epitaxy/local_... (그 세션이 있는 PC에서만 열림)
클로드 웹 대화: https://claude.ai/chat/...
"""
from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMenu, QMessageBox, QToolButton, QVBoxLayout,
)

import theme

HINT = ("클로드 세션 링크를 붙여넣으세요.\n"
        "· 가장 쉬운 방법: 그 세션에서 클로드에게 \"이 세션을 아이디어 보드의 ○○에 연결해줘\"라고 하기\n"
        "· 클로드 앱 세션 링크(claude://…)는 그 세션이 있는 PC에서만 열려요.")


def looks_like_link(text):
    t = (text or "").strip()
    return t.startswith(("claude://", "https://", "http://"))


class LinkDialog(QDialog):
    def __init__(self, label="", url="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("클로드 세션 연결")
        self.setMinimumWidth(520)
        self.label = QLineEdit(label)
        self.label.setPlaceholderText("예: PC 버전 개발 세션")
        self.url = QLineEdit(url)
        self.url.setPlaceholderText("claude://claude.ai/epitaxy/local_…  또는  https://claude.ai/chat/…")
        if not url:
            clip = QGuiApplication.clipboard().text()
            if looks_like_link(clip):
                self.url.setText(clip.strip())      # 복사해 둔 링크가 있으면 미리 채움
        form = QFormLayout()
        form.addRow("이름", self.label)
        form.addRow("링크", self.url)
        hint = QLabel(HINT)
        hint.setWordWrap(True)
        hint.setStyleSheet("color:%s;" % theme.TEXT_DIM)
        buttons = QDialogButtonBox()
        self.ok = buttons.addButton("저장", QDialogButtonBox.AcceptRole)
        buttons.addButton("취소", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.url.textChanged.connect(lambda t: self.ok.setEnabled(looks_like_link(t)))
        self.ok.setEnabled(looks_like_link(self.url.text()))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.addLayout(form)
        lay.addWidget(hint)
        lay.addWidget(buttons)

    def values(self):
        return self.label.text().strip(), self.url.text().strip()


class LinkButton(QToolButton):
    """'🔗 클로드 세션 n' 버튼: 누르면 연결된 링크 목록 + 추가·고치기·지우기."""
    changed = Signal(str)

    def __init__(self, store_, parent=None):
        super().__init__(parent)
        self.store = store_
        self.uid = None
        self.setPopupMode(QToolButton.InstantPopup)
        self.setToolTip("이 아이디어와 연결한 클로드 세션 열기")
        self.setStyleSheet("QToolButton { border:1px solid %s; border-radius:10px; padding:2px 10px; }"
                           "QToolButton:hover { border-color:%s; } QToolButton::menu-indicator { image:none; }"
                           % (theme.BORDER, theme.ACCENT))
        self.menu_ = QMenu(self)
        self.menu_.aboutToShow.connect(self._build)
        self.setMenu(self.menu_)

    def load(self, uid):
        self.uid = uid
        n = len(self.store.links(uid))
        self.setText("🔗 클로드 세션 %d" % n if n else "🔗 클로드 세션 연결")

    def _build(self):
        m = self.menu_
        m.clear()
        links = self.store.links(self.uid)
        for l in links:
            name = l["label"] or l["url"]
            a = m.addAction("↗  " + name, lambda url=l["url"]: self.open(url))
            a.setToolTip(l["url"])
        if links:
            m.addSeparator()
        m.addAction("＋ 세션 링크 추가…", self._add)
        if links:
            edit = m.addMenu("고치기")
            rm = m.addMenu("지우기")
            for l in links:
                name = l["label"] or l["url"]
                edit.addAction(name, lambda l=l: self._edit(l))
                rm.addAction(name, lambda l=l: self._remove(l))
            m.addAction("링크 복사", lambda: QGuiApplication.clipboard().setText(
                "\n".join(l["url"] for l in links)))

    def open(self, url):
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(self, "링크 열기", "이 링크를 열지 못했어요.\n%s\n\n"
                                "claude:// 링크는 클로드 앱이 설치된 PC, 그 세션이 있는 PC에서만 열려요." % url)

    def _add(self):
        dlg = LinkDialog(parent=self.window())
        if dlg.exec() == QDialog.Accepted:
            label, url = dlg.values()
            self.store.add_link(self.uid, url, label)
            self._changed()

    def _edit(self, l):
        dlg = LinkDialog(l["label"], l["url"], self.window())
        if dlg.exec() == QDialog.Accepted:
            label, url = dlg.values()
            self.store.update_link(l["uuid"], label=label, url=url)
            self._changed()

    def _remove(self, l):
        if QMessageBox.question(self, "링크 지우기", "'%s' 링크를 지울까요?" % (l["label"] or l["url"])) \
                == QMessageBox.Yes:
            self.store.delete_link(l["uuid"])
            self._changed()

    def _changed(self):
        self.load(self.uid)
        self.changed.emit(self.uid)

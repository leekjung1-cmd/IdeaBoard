"""내보내기: 아이디어를 마크다운(.md)으로 저장 / 클로드로 보내기(복사 + 클로드 열기) / 전체 백업."""
import os
import re
from datetime import datetime

from PySide6.QtCore import QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QFileDialog, QMessageBox

from store import FEATURE_PRIORITIES, QUADRANTS, quadrant

LEVEL = {None: "미정", 1: "1 매우 낮음", 2: "2 낮음", 3: "3 보통", 4: "4 높음", 5: "5 매우 높음"}
CLAUDE_PROMPT = ("아래는 내 '아이디어 보드' 프로그램에 정리해 둔 아이디어야. "
                 "이 내용을 바탕으로 이어서 같이 기획하고 개발하자. 먼저 내용을 읽고 빠진 점이나 질문이 있으면 말해줘.\n\n")


def _when(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M")


def idea_markdown(store, uid):
    r = store.get(uid)
    if r is None:
        return ""
    out = ["# %s" % (r["title"] or "(제목 없음)"), ""]
    if r["summary"]:
        out += ["> %s" % r["summary"], ""]
    q = quadrant(r["importance"], r["urgency"])
    out += [
        "- 상태: %s" % r["status"],
        "- 다음 한 걸음: %s" % (r["next_step"] or "(안 정함)"),
        "- 분류: %s" % (r["category"] or "안 정함"),
        "- 중요도: %s / 긴급도: %s → %s" % (LEVEL[r["importance"]], LEVEL[r["urgency"]], QUADRANTS[q]),
        "- 일정: 시작 %s / 목표 %s" % (r["start_date"] or "미정", r["due_date"] or "미정"),
        "",
        "## 기획서",
        "",
    ]
    for s in store.sections(uid):
        out.append("### %s" % (s["title"] or "(제목 없음)"))
        out += [s["content"].strip() or "_(비어 있음)_", ""]

    feats = store.features(uid)
    if feats:
        out += ["## 필요한 기능", ""]
        for pr in FEATURE_PRIORITIES:
            group = [f for f in feats if f["priority"] == pr]
            if group:
                out.append("**%s**" % pr)
                for f in group:
                    out.append("- [%s] %s" % ("x" if f["done"] else " ", f["text"]))
                    if f["criteria"].strip():
                        out.append("  - 확인: %s" % f["criteria"].strip())
                out.append("")

    memos = store.memos(uid)
    if memos:
        out += ["## 메모", ""]
        for m in memos:
            body = m["body"].strip().replace("\n", "\n  ")
            out.append("- (%s) %s" % (_when(m["created_at"]), body))
        out.append("")

    links = store.links(uid)
    if links:
        out += ["## 클로드 세션·링크", ""]
        out += ["- %s: %s" % (l["label"] or "링크", l["url"]) for l in links]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def safe_name(title):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', " ", title or "제목 없음").strip().rstrip(".")
    return (name or "제목 없음")[:80]


def _docs_dir():
    return QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or os.path.expanduser("~")


def save_idea(parent, store, uid):
    r = store.get(uid)
    if r is None:
        return
    path, _ = QFileDialog.getSaveFileName(parent, "마크다운으로 내보내기",
                                          os.path.join(_docs_dir(), safe_name(r["title"]) + ".md"),
                                          "마크다운 (*.md);;텍스트 (*.txt)")
    if not path:
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(idea_markdown(store, uid))
    QMessageBox.information(parent, "내보내기", "저장했어요.\n%s" % path)


def export_all(parent, store):
    folder = QFileDialog.getExistingDirectory(parent, "모든 아이디어를 내보낼 폴더", _docs_dir())
    if not folder:
        return
    folder = os.path.join(folder, "아이디어 보드 내보내기 %s" % datetime.now().strftime("%Y-%m-%d %H%M"))
    os.makedirs(folder, exist_ok=True)
    rows = store.ideas()
    used = set()
    index = ["# 아이디어 목록", "", "| 아이디어 | 상태 | 분류 | 사분면 | 목표일 |", "|---|---|---|---|---|"]
    for r in rows:
        name = safe_name(r["title"])
        base, n = name, 2
        while name.lower() in used:
            name = "%s (%d)" % (base, n)
            n += 1
        used.add(name.lower())
        with open(os.path.join(folder, name + ".md"), "w", encoding="utf-8") as f:
            f.write(idea_markdown(store, r["uuid"]))
        index.append("| [%s](%s) | %s | %s | %s | %s |" % (
            (r["title"] or "(제목 없음)").replace("|", "/"), QUrl.toPercentEncoding(name + ".md").data().decode(),
            r["status"], r["category"] or "-", QUADRANTS[quadrant(r["importance"], r["urgency"])],
            r["due_date"] or "-"))
    with open(os.path.join(folder, "_목록.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(index) + "\n")
    QMessageBox.information(parent, "내보내기", "아이디어 %d개를 내보냈어요.\n%s" % (len(rows), folder))
    QDesktopServices.openUrl(QUrl.fromLocalFile(folder))


def backup(parent, store):
    path, _ = QFileDialog.getSaveFileName(
        parent, "백업 파일 만들기",
        os.path.join(_docs_dir(), "아이디어보드-백업-%s.db" % datetime.now().strftime("%Y%m%d-%H%M")),
        "아이디어 보드 백업 (*.db)")
    if not path:
        return
    store.backup_to(path)
    QMessageBox.information(parent, "백업", "백업했어요.\n%s\n\n되살릴 때는 프로그램을 끄고 이 파일을 "
                                         "data 폴더의 ideas.db 자리에 넣으면 돼요." % path)


def send_to_claude(parent, store, uid, prompt=CLAUDE_PROMPT):
    """부탁 글 + 기획서·기능·메모를 클립보드에 복사하고 클로드 앱을 연다."""
    QGuiApplication.clipboard().setText(prompt + idea_markdown(store, uid))
    opened = QDesktopServices.openUrl(QUrl("claude://"))
    QMessageBox.information(
        parent, "클로드로 보내기",
        "이 아이디어 내용을 복사했어요.\n" +
        ("클로드 앱이 열리면 새 대화(세션)에 붙여넣기(Ctrl+V) 하세요." if opened else
         "클로드 앱을 열지 못했어요. 클로드를 직접 열고 새 대화에 붙여넣기(Ctrl+V) 하세요."))

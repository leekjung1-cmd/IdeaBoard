"""데이터 위치와 업데이트 대비.

새 버전을 어느 폴더에 풀어도 같은 기록을 쓰도록 데이터는 사용자 폴더(%APPDATA%\\IdeaBoard) 한 곳에 둔다.
- 예전 버전처럼 exe 옆 data 폴더에 기록이 있으면 처음 한 번 가져온다.
- 프로그램 버전이 바뀐 뒤 처음 켤 때 자동 백업 (backups 폴더, 최근 10개만 남김).
"""
import glob
import json
import os
import sqlite3
from datetime import datetime

KEEP_BACKUPS = 10


def default_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "IdeaBoard")


def copy_db(src, dst):
    """SQLite 파일 안전하게 복사 (쓰는 중이어도 됨)."""
    a = sqlite3.connect(src)
    b = sqlite3.connect(dst)
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()


def backup_now(data_dir, tag):
    db = os.path.join(data_dir, "ideas.db")
    if not os.path.exists(db):
        return None
    folder = os.path.join(data_dir, "backups")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "ideas-%s-%s.db" % (tag, datetime.now().strftime("%Y%m%d-%H%M%S")))
    copy_db(db, path)
    old = sorted(glob.glob(os.path.join(folder, "ideas-*.db")), key=os.path.getmtime)
    for p in old[:-KEEP_BACKUPS]:
        try:
            os.remove(p)
        except OSError:
            pass
    return path


def prepare(data_dir, legacy_dir, version):
    """프로그램 켜기 전에 부름. 사용자에게 알릴 말 목록을 돌려줌."""
    notes = []
    os.makedirs(data_dir, exist_ok=True)
    db = os.path.join(data_dir, "ideas.db")
    settings_path = os.path.join(data_dir, "settings.json")

    legacy_db = os.path.join(legacy_dir, "ideas.db")
    same = os.path.normcase(os.path.abspath(legacy_dir)) == os.path.normcase(os.path.abspath(data_dir))
    if not os.path.exists(db) and os.path.exists(legacy_db) and not same:
        copy_db(legacy_db, db)
        legacy_settings = os.path.join(legacy_dir, "settings.json")
        if os.path.exists(legacy_settings) and not os.path.exists(settings_path):
            with open(legacy_settings, encoding="utf-8") as f, open(settings_path, "w", encoding="utf-8") as g:
                g.write(f.read())
        notes.append("예전 기록을 가져왔어요.\n%s  →  %s" % (legacy_dir, data_dir))

    try:
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
    except (OSError, ValueError):
        settings = {}
    last = settings.get("last_version")
    if last != version:
        if os.path.exists(db) and last:
            backup_now(data_dir, "v" + last)        # 새 버전으로 처음 켜기 전 상태
        settings["last_version"] = version
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
    return notes

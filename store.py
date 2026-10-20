"""아이디어 보드 저장소 (SQLite).

나중에 폰과 동기화할 수 있게 모든 행에 uuid·updated_at(밀리초)·deleted를 둔다.
삭제는 지우지 않고 deleted=1 (동기화 때 상대편에도 삭제를 알리기 위해).
"""
import os
import sqlite3
import time
import uuid

# 상태 (v1.6.0~): 진행 중은 ACTIVE_LIMIT 개까지만. 새 아이디어는 보관함에서 시작.
STATUSES = ["보관함", "진행 중", "완료", "보류"]
ACTIVE = "진행 중"
ACTIVE_LIMIT = 3
# 예전 상태 이름 → 지금 이름 (예전 파일·예전 폰 앱에서 온 값도 이걸로 바꿔 받음)
OLD_STATUS = {"아이디어": "보관함", "기획": "보관함", "개발 중": "진행 중"}


def norm_status(st):
    return OLD_STATUS.get(st, st)
# 분류 = 목표 (v1.7.0~). 직접 입력한 것도 쓸 수 있음
CATEGORIES = ["클로드 실력", "수익화", "네트워크", "운동", "기타"]
OLD_CATEGORIES = {"일상", "취미", "업무", "공용", "미래의 목표", "미래의목표"}

# 주간 시간표: 평일(월~금) 밤 9시 반부터 30분씩
WEEKDAYS = ["월", "화", "수", "목", "금"]
SLOTS = ["21:30", "22:00", "22:30", "23:00", "23:30"]
LEVELS = [1, 2, 3, 4, 5]          # 중요도·긴급도
HIGH = 4                          # 이 값 이상이면 '높음'

# 사분면 번호: 1 지금 할 것 / 2 계획할 것 / 3 빨리 끝낼 것 / 4 나중에 / 0 미분류
QUADRANTS = {1: "지금 할 것", 2: "계획할 것", 3: "빨리 끝낼 것", 4: "나중에", 0: "미분류"}

# 기획서 틀: (키, 제목, 도움말). '한 줄 요약'은 ideas.summary 에 있음.
# 새 아이디어 기획서 기본 칸 (v1.1.0~). 칸은 아이디어마다 따로 저장되니 바꿔도 예전 아이디어는 그대로.
BRIEF_FIELDS = [
    ("intent", "개발 의도", "왜 만들려고 하나? 어떤 불편을 해결하고, 누가 쓰나?"),
    ("features", "기능", "어떤 기능이 있어야 하나? (자세한 목록은 '필요한 기능' 탭)"),
    ("tech", "플랫폼 · 기술", "윈도우 / 안드로이드 / 크롬 확장 … 쓸 기술"),
]

# 예전(v1.0.x) 기본 칸 8개 — 예전 아이디어 칸의 도움말과 아주 옛날 파일 옮기기에만 씀
LEGACY_BRIEF_FIELDS = [
    ("problem", "문제·불편", "지금 뭐가 불편한가? 지금은 어떻게 해결하고 있나?"),
    ("users", "누가 쓰나", "나 혼자? 가족? 다른 사람들도?"),
    ("mvp", "첫 버전 핵심 기능", "이것만 되면 쓸 수 있다 싶은 최소한의 기능"),
    ("later", "나중에 할 것 · 안 할 것", "욕심나지만 첫 버전에서는 뺄 것"),
    ("similar", "비슷한 기존 앱", "이미 있는 앱·프로그램과 아쉬운 점"),
    ("tech", "플랫폼 · 기술", "윈도우 / 안드로이드 / 크롬 확장 … 쓸 기술"),
    ("done", "완성 기준", "어떻게 되면 '다 만들었다'고 할 수 있나"),
    ("questions", "미정 · 궁금한 점", "아직 못 정한 것, 알아봐야 할 것"),
]

# 개발 프로젝트로 표시한 아이디어에만 기획서에 더 넣는 칸
DEV_SECTIONS = [
    ("dev_users", "누가 쓰나", "나 혼자? 가족? 어떤 상황에서 쓰나?"),
    ("dev_not_now", "첫 버전에서 뺄 것", "욕심나지만 처음엔 안 만들 것. 이걸 정해 둬야 끝까지 만들 수 있어요"),
    ("dev_done", "다 만들었다고 할 기준", "어떻게 되면 '첫 버전 완성'인가? (예: 폰에서 적은 게 PC에 뜬다)"),
]

IDEA_COLUMNS = ("title", "summary", "status", "category", "importance", "urgency",
                "start_date", "due_date", "dev", "dev_folder", "next_step", "shorts")

SCHEMA = """
CREATE TABLE IF NOT EXISTS ideas(
    uuid TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '보관함',
    category TEXT NOT NULL DEFAULT '',      -- 용도 (일상/취미/업무/공용/직접 입력), '' = 안 정함
    dev INTEGER NOT NULL DEFAULT 0,         -- 1 = 개발 프로젝트 (개발 탭·완성 기준 등을 보여줌)
    dev_folder TEXT NOT NULL DEFAULT '',    -- 개발 시작 때 만든 폴더 (PC)
    next_step TEXT NOT NULL DEFAULT '',     -- 다음 한 걸음: 30분 안에 끝낼 다음 행동 1개
    shorts INTEGER NOT NULL DEFAULT 0,      -- 1 = 쇼츠(짧은 영상) 소재
    importance INTEGER,             -- 1~5, NULL = 미정
    urgency INTEGER,                -- 1~5, NULL = 미정
    start_date TEXT,                -- 'YYYY-MM-DD' 또는 NULL
    due_date TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);
-- 기획서 칸 (아이디어마다 따로). key = 기본 칸이면 BRIEF_FIELDS 키, 직접 만든 칸이면 NULL
CREATE TABLE IF NOT EXISTS sections(
    uuid TEXT PRIMARY KEY,
    idea_uuid TEXT NOT NULL,
    key TEXT,
    title TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    position REAL NOT NULL,
    updated_at INTEGER NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS sections_idea ON sections(idea_uuid, position);
-- 예전(칸 고정) 기획서. 처음 열 때 sections 로 옮겨감
CREATE TABLE IF NOT EXISTS brief(
    idea_uuid TEXT NOT NULL,
    key TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    updated_at INTEGER NOT NULL,
    PRIMARY KEY(idea_uuid, key)
);
CREATE TABLE IF NOT EXISTS memos(
    uuid TEXT PRIMARY KEY,
    idea_uuid TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS memos_idea ON memos(idea_uuid, created_at);
-- 필요한 기능 목록. priority = FEATURE_PRIORITIES 중 하나
CREATE TABLE IF NOT EXISTS features(
    uuid TEXT PRIMARY KEY,
    idea_uuid TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT '필수',
    done INTEGER NOT NULL DEFAULT 0,
    criteria TEXT NOT NULL DEFAULT '',      -- 완성 기준: 다 됐는지 확인하는 법 (개발 프로젝트)
    position REAL NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS features_idea ON features(idea_uuid, position);
-- 클로드 세션 등 바로가기 링크
CREATE TABLE IF NOT EXISTS links(
    uuid TEXT PRIMARY KEY,
    idea_uuid TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS links_idea ON links(idea_uuid, created_at);
-- 할일 (포스트잇). idea_uuid = 관련 아이디어(없어도 됨), x·y = 벽에 붙인 자리
CREATE TABLE IF NOT EXISTS todos(
    uuid TEXT PRIMARY KEY,
    text TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT 'yellow',
    done INTEGER NOT NULL DEFAULT 0,
    due_date TEXT,
    idea_uuid TEXT,
    x REAL,
    y REAL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);
-- 주간 시간표: weekday 0=월 … 4=금, slot = SLOTS 순번. 칸 하나에 아이디어 하나
CREATE TABLE IF NOT EXISTS timetable(
    uuid TEXT PRIMARY KEY,
    weekday INTEGER NOT NULL,
    slot INTEGER NOT NULL,
    idea_uuid TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0
);
"""

TODO_COLORS = ["yellow", "pink", "green", "blue", "orange", "purple"]

FEATURE_PRIORITIES = ["필수", "있으면 좋음", "나중에"]

# 저장 파일 구조 번호 (PRAGMA user_version). 1 = v1.0.0 (용도·필요한 기능·링크까지)
# 2 = v1.2.1 (동기화 표마다 pc_seen: PC가 그 행을 받거나 합친 시각 → 폰 여러 대가 서로의 변경을 놓치지 않게)
# 3 = v1.3.0 (할일 todos)
# 4 = v1.5.0 (개발 프로젝트: ideas.dev·dev_folder, features.criteria)
# 5 = v1.6.0 (ideas.next_step, 상태 이름 바꿈: 아이디어·기획 → 보관함, 개발 중 → 진행 중)
# 6 = v1.7.0 (ideas.shorts, 주간 시간표 timetable)
SCHEMA_VERSION = 6


def now_ms():
    return int(time.time() * 1000)


def quadrant(importance, urgency):
    if importance is None or urgency is None:
        return 0
    imp, urg = importance >= HIGH, urgency >= HIGH
    if imp and urg:
        return 1
    if imp:
        return 2
    if urg:
        return 3
    return 4


class Store:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._migrate()
        self.db.commit()

    def _migrate(self):
        """예전 파일에 없는 칸 추가하고 파일에 구조 번호(user_version) 기록.
        구조가 바뀌면 SCHEMA_VERSION 을 올리고 여기에 옮기는 코드를 더한다."""
        ver = self.db.execute("PRAGMA user_version").fetchone()[0]
        self.newer_file = ver > SCHEMA_VERSION      # 더 새 버전 프로그램이 만든 파일
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(ideas)")}
        if "category" not in cols:
            self.db.execute("ALTER TABLE ideas ADD COLUMN category TEXT NOT NULL DEFAULT ''")
        if "dev" not in cols:
            self.db.execute("ALTER TABLE ideas ADD COLUMN dev INTEGER NOT NULL DEFAULT 0")
        if "dev_folder" not in cols:
            self.db.execute("ALTER TABLE ideas ADD COLUMN dev_folder TEXT NOT NULL DEFAULT ''")
        if "criteria" not in {r["name"] for r in self.db.execute("PRAGMA table_info(features)")}:
            self.db.execute("ALTER TABLE features ADD COLUMN criteria TEXT NOT NULL DEFAULT ''")
        if "next_step" not in cols:
            self.db.execute("ALTER TABLE ideas ADD COLUMN next_step TEXT NOT NULL DEFAULT ''")
        if "shorts" not in cols:
            self.db.execute("ALTER TABLE ideas ADD COLUMN shorts INTEGER NOT NULL DEFAULT 0")
        if ver < 5:
            # 상태 이름만 바꿈 (고친 시각은 그대로 → 폰과 주고받을 때 괜히 '바뀜'으로 안 잡힘. 폰 앱도 같은 규칙으로 바꿔 읽음)
            for old, new in OLD_STATUS.items():
                self.db.execute("UPDATE ideas SET status=? WHERE status=?", (new, old))
        for t in self.SYNC_TABLES:
            if "pc_seen" not in {r["name"] for r in self.db.execute("PRAGMA table_info(%s)" % t)}:
                self.db.execute("ALTER TABLE %s ADD COLUMN pc_seen INTEGER NOT NULL DEFAULT 0" % t)
        if ver < SCHEMA_VERSION:
            self.db.execute("PRAGMA user_version=%d" % SCHEMA_VERSION)

    def categories(self):
        """기본 용도 + 직접 입력해서 쓰고 있는 용도."""
        used = [r[0] for r in self.db.execute(
            "SELECT DISTINCT category FROM ideas WHERE deleted=0 AND category<>'' ORDER BY category")]
        return CATEGORIES + [c for c in used if c not in CATEGORIES]

    # ---------- 아이디어 ----------
    def ideas(self, query=""):
        """삭제 안 된 아이디어, 최근 활동 순. query 는 제목·요약·기획서·메모에서 찾음."""
        sql = """
            SELECT i.*, MAX(i.updated_at,
                IFNULL((SELECT MAX(updated_at) FROM sections WHERE idea_uuid=i.uuid), 0),
                IFNULL((SELECT MAX(updated_at) FROM memos WHERE idea_uuid=i.uuid AND deleted=0), 0),
                IFNULL((SELECT MAX(updated_at) FROM features WHERE idea_uuid=i.uuid), 0)
            ) AS activity
            FROM ideas i WHERE i.deleted=0"""
        args = []
        q = query.strip()
        if q:
            like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            sql += """ AND (i.title LIKE ? ESCAPE '\\' OR i.summary LIKE ? ESCAPE '\\' OR i.category LIKE ? ESCAPE '\\'
                OR EXISTS(SELECT 1 FROM sections b WHERE b.idea_uuid=i.uuid AND b.deleted=0
                          AND (b.content LIKE ? ESCAPE '\\' OR b.title LIKE ? ESCAPE '\\'))
                OR EXISTS(SELECT 1 FROM memos m WHERE m.idea_uuid=i.uuid AND m.deleted=0
                          AND m.body LIKE ? ESCAPE '\\')
                OR EXISTS(SELECT 1 FROM features f WHERE f.idea_uuid=i.uuid AND f.deleted=0
                          AND f.text LIKE ? ESCAPE '\\'))"""
            args = [like] * 7
        sql += " ORDER BY activity DESC"
        return self.db.execute(sql, args).fetchall()

    def get(self, uid):
        return self.db.execute("SELECT * FROM ideas WHERE uuid=? AND deleted=0", (uid,)).fetchone()

    def create(self, title, **fields):
        uid = str(uuid.uuid4())
        t = now_ms()
        self.db.execute("INSERT INTO ideas(uuid, title, status, created_at, updated_at) VALUES(?,?,?,?,?)",
                        (uid, title.strip(), STATUSES[0], t, t))
        if fields:
            self._set(uid, fields, t)
        self._default_sections(uid, {}, t)
        self.db.commit()
        return uid

    def update(self, uid, **fields):
        if fields:
            self._set(uid, fields, now_ms())
            self.db.commit()

    def _set(self, uid, fields, t):
        bad = set(fields) - set(IDEA_COLUMNS)
        if bad:
            raise ValueError("모르는 항목: %s" % ", ".join(sorted(bad)))
        cols = ", ".join("%s=?" % k for k in fields)
        self.db.execute("UPDATE ideas SET %s, updated_at=? WHERE uuid=?" % cols,
                        list(fields.values()) + [t, uid])

    def delete(self, uid):
        self.delete_many([uid])

    def delete_many(self, uids):
        t = now_ms()
        self.db.executemany("UPDATE ideas SET deleted=1, updated_at=? WHERE uuid=?", [(t, u) for u in uids])
        self.db.commit()

    # ---------- 진행 중 (최대 ACTIVE_LIMIT 개) · 다음 한 걸음 ----------
    def active_ideas(self):
        return self.db.execute("SELECT * FROM ideas WHERE deleted=0 AND status=? ORDER BY updated_at",
                               (ACTIVE,)).fetchall()

    def room_needed(self, uids, new=0):
        """uids(+새로 만들 new 개)를 진행 중으로 올리려면 더 비워야 할 자리 수 (0 = 바로 가능)."""
        active = {r["uuid"] for r in self.active_ideas()}
        adding = len(set(uids) - active) + new
        return max(0, len(active) + adding - ACTIVE_LIMIT) if adding else 0

    def finish_step(self, uid):
        """다음 한 걸음 끝냄: 메모에 기록하고 칸을 비움. 돌려주는 값: 끝낸 글 (없으면 '')"""
        row = self.get(uid)
        step = (row["next_step"] if row is not None else "").strip()
        if not step:
            return ""
        self.add_memo(uid, "✅ 한 걸음 끝: " + step)
        self.update(uid, next_step="")
        return step

    # ---------- 주간 점검 ----------
    def touch(self, uid):
        """'계속' 고름: 손댄 것으로 침 (오래 손 안 댄 것에서 빠짐)."""
        self.db.execute("UPDATE ideas SET updated_at=? WHERE uuid=?", (now_ms(), uid))
        self.db.commit()

    def old_category_ideas(self):
        """예전 분류(일상·취미·업무…)나 분류 없음인 아이디어."""
        return [r for r in self.ideas() if r["category"] not in CATEGORIES]

    # ---------- 주간 시간표 ----------
    def timetable(self):
        """{(요일, 칸): 행} — 지워진 아이디어 칸은 뺌. 행에는 아이디어 제목·다음 한 걸음도."""
        rows = self.db.execute("""SELECT t.*, i.title, i.next_step, i.status, i.importance, i.urgency
                                  FROM timetable t JOIN ideas i ON i.uuid=t.idea_uuid AND i.deleted=0
                                  WHERE t.deleted=0""").fetchall()
        return {(r["weekday"], r["slot"]): r for r in rows}

    def set_slot(self, weekday, slot, idea_uuid):
        """칸에 아이디어 놓기 (idea_uuid=None 이면 비우기). 그 칸에 있던 건 지움."""
        t = now_ms()
        self.db.execute("UPDATE timetable SET deleted=1, updated_at=? WHERE weekday=? AND slot=? AND deleted=0",
                        (t, weekday, slot))
        if idea_uuid:
            self.db.execute("INSERT INTO timetable(uuid, weekday, slot, idea_uuid, updated_at) VALUES(?,?,?,?,?)",
                            (str(uuid.uuid4()), weekday, slot, idea_uuid, t))
        self.db.commit()

    def set_status_many(self, uids, status):
        """여러 아이디어 상태를 한꺼번에. 이미 그 상태인 건 건드리지 않음."""
        t = now_ms()
        self.db.executemany("UPDATE ideas SET status=?, updated_at=? WHERE uuid=? AND status<>?",
                            [(status, t, u, status) for u in uids])
        self.db.commit()

    def add_dev_sections(self, uid):
        """개발 프로젝트용 기획서 칸 중 없는 것만 맨 아래에 추가. 돌려주는 값: 추가한 칸 수"""
        rows = self.sections(uid)
        have = {r["key"] for r in rows}
        pos = (rows[-1]["position"] if rows else 0) + 1
        t = now_ms()
        n = 0
        for key, label, _hint in DEV_SECTIONS:
            if key in have:
                continue
            self.db.execute("""INSERT INTO sections(uuid, idea_uuid, key, title, content, position, updated_at)
                               VALUES(?,?,?,?,'',?,?)""", (str(uuid.uuid4()), uid, key, label, pos, t))
            pos += 1
            n += 1
        self.db.commit()
        return n

    # ---------- 기획서 칸 ----------
    def _default_sections(self, uid, old, t):
        # old = 아주 옛날(칸 고정) 기획서 내용 → 그때 칸 8개 그대로 옮김. 새 아이디어면 새 기본 칸.
        fields = LEGACY_BRIEF_FIELDS if old else BRIEF_FIELDS
        for i, (key, label, _hint) in enumerate(fields):
            self.db.execute("""INSERT INTO sections(uuid, idea_uuid, key, title, content, position, updated_at)
                               VALUES(?,?,?,?,?,?,?)""",
                            (str(uuid.uuid4()), uid, key, label, old.get(key, ""), float(i + 1), t))

    def delete_sections(self, sids):
        t = now_ms()
        self.db.executemany("UPDATE sections SET deleted=1, updated_at=? WHERE uuid=?", [(t, sid) for sid in sids])
        self.db.commit()

    def sections(self, uid):
        """칸 목록 (순서대로). 칸이 하나도 없던 예전 아이디어면 기본 칸을 만들어 넣음."""
        rows = self.db.execute("SELECT * FROM sections WHERE idea_uuid=? AND deleted=0 ORDER BY position",
                               (uid,)).fetchall()
        if rows or self.db.execute("SELECT 1 FROM sections WHERE idea_uuid=? LIMIT 1", (uid,)).fetchone():
            return rows
        old = {r["key"]: r["content"] for r in
               self.db.execute("SELECT key, content FROM brief WHERE idea_uuid=?", (uid,))}
        self._default_sections(uid, old, now_ms())
        self.db.commit()
        return self.sections(uid)

    def add_section(self, uid, title="", after=None):
        """새 칸. after(칸 uuid) 가 있으면 그 바로 아래, 없으면 맨 아래."""
        rows = self.sections(uid)
        pos = (rows[-1]["position"] + 1) if rows else 1.0
        if after:
            for i, r in enumerate(rows):
                if r["uuid"] == after:
                    nxt = rows[i + 1]["position"] if i + 1 < len(rows) else r["position"] + 2
                    pos = (r["position"] + nxt) / 2
                    break
        sid = str(uuid.uuid4())
        self.db.execute("""INSERT INTO sections(uuid, idea_uuid, key, title, content, position, updated_at)
                           VALUES(?,?,NULL,?,'',?,?)""", (sid, uid, title, pos, now_ms()))
        self.db.commit()
        return sid

    def update_section(self, sid, title=None, content=None):
        fields = {}
        if title is not None:
            fields["title"] = title
        if content is not None:
            fields["content"] = content
        if fields:
            cols = ", ".join("%s=?" % k for k in fields)
            self.db.execute("UPDATE sections SET %s, updated_at=? WHERE uuid=?" % cols,
                            list(fields.values()) + [now_ms(), sid])
            self.db.commit()

    def append_to_section(self, sid, text):
        row = self.db.execute("SELECT content FROM sections WHERE uuid=?", (sid,)).fetchone()
        if row is not None:
            cur = row["content"].rstrip()
            self.update_section(sid, content=(cur + "\n" + text) if cur else text)

    def delete_section(self, sid):
        self.db.execute("UPDATE sections SET deleted=1, updated_at=? WHERE uuid=?", (now_ms(), sid))
        self.db.commit()

    def move_section(self, sid, step):
        """step = -1 위로, +1 아래로 (옆 칸과 자리 바꿈)."""
        row = self.db.execute("SELECT idea_uuid FROM sections WHERE uuid=?", (sid,)).fetchone()
        if row is None:
            return
        rows = self.sections(row["idea_uuid"])
        idx = next(i for i, r in enumerate(rows) if r["uuid"] == sid)
        j = idx + step
        if not 0 <= j < len(rows):
            return
        t = now_ms()
        a, b = rows[idx], rows[j]
        self.db.execute("UPDATE sections SET position=?, updated_at=? WHERE uuid=?", (b["position"], t, a["uuid"]))
        self.db.execute("UPDATE sections SET position=?, updated_at=? WHERE uuid=?", (a["position"], t, b["uuid"]))
        self.db.commit()

    # ---------- 메모 ----------
    def memos(self, uid):
        return self.db.execute("SELECT * FROM memos WHERE idea_uuid=? AND deleted=0 ORDER BY created_at",
                               (uid,)).fetchall()

    def add_memo(self, uid, body):
        mid = str(uuid.uuid4())
        t = now_ms()
        self.db.execute("INSERT INTO memos(uuid, idea_uuid, body, created_at, updated_at) VALUES(?,?,?,?,?)",
                        (mid, uid, body, t, t))
        self.db.commit()
        return mid

    def update_memo(self, mid, body):
        self.db.execute("UPDATE memos SET body=?, updated_at=? WHERE uuid=?", (body, now_ms(), mid))
        self.db.commit()

    def delete_memo(self, mid):
        self.db.execute("UPDATE memos SET deleted=1, updated_at=? WHERE uuid=?", (now_ms(), mid))
        self.db.commit()

    # ---------- 필요한 기능 ----------
    def features(self, uid):
        return self.db.execute("SELECT * FROM features WHERE idea_uuid=? AND deleted=0 ORDER BY position",
                               (uid,)).fetchall()

    def add_feature(self, uid, text, priority=FEATURE_PRIORITIES[0]):
        row = self.db.execute("SELECT MAX(position) FROM features WHERE idea_uuid=?", (uid,)).fetchone()
        pos = (row[0] or 0) + 1
        fid = str(uuid.uuid4())
        t = now_ms()
        self.db.execute("""INSERT INTO features(uuid, idea_uuid, text, priority, position, created_at, updated_at)
                           VALUES(?,?,?,?,?,?,?)""", (fid, uid, text, priority, pos, t, t))
        self.db.commit()
        return fid

    def update_feature(self, fid, **fields):
        bad = set(fields) - {"text", "priority", "done", "criteria"}
        if bad:
            raise ValueError("모르는 항목: %s" % ", ".join(sorted(bad)))
        if fields:
            cols = ", ".join("%s=?" % k for k in fields)
            self.db.execute("UPDATE features SET %s, updated_at=? WHERE uuid=?" % cols,
                            list(fields.values()) + [now_ms(), fid])
            self.db.commit()

    def delete_feature(self, fid):
        self.db.execute("UPDATE features SET deleted=1, updated_at=? WHERE uuid=?", (now_ms(), fid))
        self.db.commit()

    def move_feature(self, fid, step):
        """같은 중요도 묶음 안에서 위(-1)·아래(+1) 칸과 자리 바꿈."""
        row = self.db.execute("SELECT idea_uuid, priority FROM features WHERE uuid=?", (fid,)).fetchone()
        if row is None:
            return
        rows = [r for r in self.features(row["idea_uuid"]) if r["priority"] == row["priority"]]
        idx = next(i for i, r in enumerate(rows) if r["uuid"] == fid)
        j = idx + step
        if not 0 <= j < len(rows):
            return
        t = now_ms()
        a, b = rows[idx], rows[j]
        self.db.execute("UPDATE features SET position=?, updated_at=? WHERE uuid=?", (b["position"], t, a["uuid"]))
        self.db.execute("UPDATE features SET position=?, updated_at=? WHERE uuid=?", (a["position"], t, b["uuid"]))
        self.db.commit()

    # ---------- 링크 (클로드 세션 등) ----------
    def links(self, uid):
        return self.db.execute("SELECT * FROM links WHERE idea_uuid=? AND deleted=0 ORDER BY created_at",
                               (uid,)).fetchall()

    def add_link(self, uid, url, label=""):
        lid = str(uuid.uuid4())
        t = now_ms()
        self.db.execute("INSERT INTO links(uuid, idea_uuid, label, url, created_at, updated_at) VALUES(?,?,?,?,?,?)",
                        (lid, uid, label.strip(), url.strip(), t, t))
        self.db.commit()
        return lid

    def update_link(self, lid, label=None, url=None):
        fields = {k: v.strip() for k, v in (("label", label), ("url", url)) if v is not None}
        if fields:
            cols = ", ".join("%s=?" % k for k in fields)
            self.db.execute("UPDATE links SET %s, updated_at=? WHERE uuid=?" % cols,
                            list(fields.values()) + [now_ms(), lid])
            self.db.commit()

    def delete_link(self, lid):
        self.db.execute("UPDATE links SET deleted=1, updated_at=? WHERE uuid=?", (now_ms(), lid))
        self.db.commit()

    # ---------- 백업 ----------
    def backup_to(self, path):
        """지금 데이터 전체를 다른 파일로 복사 (쓰는 중이어도 안전한 SQLite 백업)."""
        dst = sqlite3.connect(path)
        try:
            self.db.backup(dst)
        finally:
            dst.close()

    # ---------- 다른 파일(예전 데이터·백업·다른 PC)과 합치기 ----------
    MERGE_TABLES = (("ideas", ("uuid",)), ("sections", ("uuid",)), ("memos", ("uuid",)),
                    ("features", ("uuid",)), ("links", ("uuid",)), ("todos", ("uuid",)), ("timetable", ("uuid",)),
                    ("brief", ("idea_uuid", "key")))

    def merge_from(self, path):
        """path 의 데이터를 지금 데이터에 합친다. 없는 건 추가, 둘 다 있으면 더 최근에 고친 쪽(updated_at)이 남음.
        예전 버전 파일이라 없는 칸·표가 있어도 됨. 돌려주는 값: (추가 수, 바뀐 수)"""
        src = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        src.row_factory = sqlite3.Row
        added = changed = 0
        try:
            src_tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "ideas" not in src_tables:
                raise ValueError("아이디어 보드 데이터 파일이 아니에요.")
            for table, keys in self.MERGE_TABLES:
                if table not in src_tables:
                    continue
                dst_cols = [r["name"] for r in self.db.execute("PRAGMA table_info(%s)" % table)]
                src_cols = {r["name"] for r in src.execute("PRAGMA table_info(%s)" % table)}
                cols = [c for c in dst_cols if c in src_cols]
                for row in src.execute("SELECT %s FROM %s" % (", ".join(cols), table)):
                    r = self._merge_row(table, keys, cols, row)
                    added += r == "added"
                    changed += r == "changed"
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        finally:
            src.close()
        return added, changed

    def _merge_row(self, table, keys, cols, row):
        """행 하나 합치기: 없으면 추가, 있으면 더 최근에 고친 쪽이 남음. 돌려주는 값: 'added' | 'changed' | None"""
        if table == "ideas" and "status" in cols:
            row = {c: row[c] for c in cols}
            row["status"] = norm_status(row["status"])
        where = " AND ".join("%s=?" % k for k in keys)
        key_vals = [row[k] for k in keys]
        cur = self.db.execute("SELECT updated_at FROM %s WHERE %s" % (table, where), key_vals).fetchone()
        if cur is None:
            self.db.execute("INSERT INTO %s(%s) VALUES(%s)" % (table, ", ".join(cols), ",".join("?" * len(cols))),
                            [row[c] for c in cols])
            result = "added"
        elif row["updated_at"] > cur["updated_at"]:
            sets = [c for c in cols if c not in keys]
            self.db.execute("UPDATE %s SET %s WHERE %s" % (table, ", ".join("%s=?" % c for c in sets), where),
                            [row[c] for c in sets] + key_vals)
            result = "changed"
        else:
            return None
        if table in self.SYNC_TABLES:     # 다른 폰이 '지난번 뒤 바뀐 것'으로 받아가게 PC 시각을 찍어 둠
            self.db.execute("UPDATE %s SET pc_seen=? WHERE %s" % (table, where), [now_ms()] + key_vals)
        return result

    def idea_count(self):
        return self.db.execute("SELECT COUNT(*) FROM ideas WHERE deleted=0").fetchone()[0]

    # ---------- 폰 동기화 ----------
    SYNC_TABLES = ("ideas", "sections", "memos", "features", "links", "todos", "timetable")

    def apply_changes(self, changes):
        """폰에서 온 {표 이름: [행…]} 합치기. 돌려주는 값: (바뀐 행 수, 영향 받은 아이디어 uuid 집합)"""
        n, touched = 0, set()
        try:
            for table in self.SYNC_TABLES:
                rows = changes.get(table) or []
                if not rows:
                    continue
                dst_cols = [r["name"] for r in self.db.execute("PRAGMA table_info(%s)" % table)]
                for row in rows:
                    if not isinstance(row, dict) or "uuid" not in row or "updated_at" not in row:
                        continue
                    cols = [c for c in dst_cols if c in row]     # 모르는 칸은 무시
                    if self._merge_row(table, ("uuid",), cols, row):
                        n += 1
                        touched.add(row["uuid"] if table == "ideas" else row.get("idea_uuid"))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return n, touched

    def changes_since(self, since):
        """since(밀리초) 뒤에 바뀐 행 전부 {표 이름: [행 dict…]} (지운 것 포함)."""
        # 아주 옛날 파일이라 기획서 칸이 아직 없는 아이디어는 칸을 만들어 둠 (폰에도 가게)
        for (uid,) in self.db.execute("""SELECT uuid FROM ideas i WHERE deleted=0 AND NOT EXISTS
                                         (SELECT 1 FROM sections s WHERE s.idea_uuid=i.uuid)""").fetchall():
            self.sections(uid)
        # updated_at 은 고친 기기의 시각, pc_seen 은 PC가 받은 시각. 밖에서 적은 뒤 늦게 들어온 것도 놓치지 않게 둘 다 봄
        return {t: [dict(r) for r in self.db.execute("SELECT * FROM %s WHERE updated_at > ? OR pc_seen > ?" % t,
                                                     (since, since))]
                for t in self.SYNC_TABLES}

    # ---------- 할일 (포스트잇) ----------
    TODO_FIELDS = ("text", "color", "done", "due_date", "idea_uuid", "x", "y")

    def todos(self):
        """삭제 안 된 할일 전부 (+ 관련 아이디어 제목)."""
        return self.db.execute("""SELECT t.*, i.title AS idea_title FROM todos t
                                  LEFT JOIN ideas i ON i.uuid=t.idea_uuid AND i.deleted=0
                                  WHERE t.deleted=0 ORDER BY t.created_at""").fetchall()

    def open_todo_count(self):
        return self.db.execute("SELECT COUNT(*) FROM todos WHERE deleted=0 AND done=0").fetchone()[0]

    def add_todo(self, text, **fields):
        tid = str(uuid.uuid4())
        t = now_ms()
        self.db.execute("INSERT INTO todos(uuid, text, created_at, updated_at) VALUES(?,?,?,?)", (tid, text.strip(), t, t))
        if fields:
            self.update_todo(tid, **fields)
        self.db.commit()
        return tid

    def update_todo(self, tid, **fields):
        bad = set(fields) - set(self.TODO_FIELDS)
        if bad:
            raise ValueError("모르는 항목: %s" % ", ".join(sorted(bad)))
        if fields:
            cols = ", ".join("%s=?" % k for k in fields)
            self.db.execute("UPDATE todos SET %s, updated_at=? WHERE uuid=?" % cols, list(fields.values()) + [now_ms(), tid])
            self.db.commit()

    def delete_todo(self, tid):
        self.db.execute("UPDATE todos SET deleted=1, updated_at=? WHERE uuid=?", (now_ms(), tid))
        self.db.commit()

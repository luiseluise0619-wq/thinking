"""
Data layer — MVP는 SQLite로 시작한다 (제로 인프라).

스키마는 ARCHITECTURE.md의 PostgreSQL 설계를 그대로 반영한다.
프로덕션 업그레이드 경로: SQLite → PostgreSQL(구조 데이터) + pgvector/Qdrant(지식 기억) + Redis(세션/큐).
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("THINKOS_DB", os.path.join(os.path.dirname(__file__), "..", "thinkos.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    password_hash TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 계정별 사고 데이터(프론트 S 블롭) — 멀티기기 동기화
CREATE TABLE IF NOT EXISTS user_state (
    user_id INTEGER PRIMARY KEY,
    state TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS thinking_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    frame TEXT,
    answer TEXT,
    framework TEXT,
    action TEXT,
    scores TEXT,           -- JSON: 8축 점수
    feedback TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Long Memory: 사용자의 가치관/강점/약점/반복 오류 (Personal Intelligence Profile)
CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER PRIMARY KEY,
    strengths TEXT,        -- JSON list
    weaknesses TEXT,       -- JSON list
    biases TEXT,           -- JSON list
    interests TEXT,        -- JSON list
    goal TEXT
);

-- Knowledge Memory (MVP: 텍스트. 프로덕션: embedding + vector DB)
CREATE TABLE IF NOT EXISTS knowledge_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    concept TEXT NOT NULL,
    relation TEXT,
    note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Wisdom Engine: 경험에서 뽑아낸 개인 원칙
CREATE TABLE IF NOT EXISTS principles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    principle TEXT NOT NULL,
    source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Feedback loop: 실행 약속 → 결과 → 교훈 (성장 OS의 핵심 고리)
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    problem TEXT,
    text TEXT NOT NULL,
    status TEXT DEFAULT 'pending',   -- pending | done | skipped
    result TEXT,
    lesson TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)
        # 기존 DB 마이그레이션 — 없는 컬럼만 추가 (best-effort)
        cols = {r["name"] for r in c.execute("PRAGMA table_info(users)")}
        for col, ddl in (("email", "email TEXT"), ("password_hash", "password_hash TEXT")):
            if col not in cols:
                c.execute(f"ALTER TABLE users ADD COLUMN {ddl}")
        # seed a demo user so the anonymous/structured endpoints work
        if not c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            c.execute("INSERT INTO users (name) VALUES (?)", ("demo",))


# ---- accounts ----
def create_user(name: str, email: str, password_hash: str) -> int:
    with conn() as c:
        return c.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
            (name, email.lower(), password_hash)).lastrowid


def user_by_email(email: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()
    return dict(r) if r else None


def user_by_id(uid: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT id, name, email, created_at FROM users WHERE id=?", (uid,)).fetchone()
    return dict(r) if r else None


# ---- per-user state (multi-device sync) ----
def get_state(uid: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT state FROM user_state WHERE user_id=?", (uid,)).fetchone()
    return json.loads(r["state"]) if r and r["state"] else None


def put_state(uid: int, state: dict) -> None:
    with conn() as c:
        c.execute(
            """INSERT INTO user_state (user_id, state, updated_at)
               VALUES (?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET state=excluded.state, updated_at=CURRENT_TIMESTAMP""",
            (uid, json.dumps(state, ensure_ascii=False)))


def all_states() -> list[dict]:
    """검증/코호트 집계용 — 모든 계정의 state."""
    with conn() as c:
        rows = c.execute(
            """SELECT u.id, u.email, s.state, s.updated_at
               FROM user_state s JOIN users u ON u.id=s.user_id""").fetchall()
    out = []
    for r in rows:
        try:
            out.append({"uid": r["id"], "email": r["email"],
                        "updated_at": r["updated_at"], "state": json.loads(r["state"] or "{}")})
        except Exception:
            pass
    return out


# ---- thinking sessions ----
def save_session(user_id: int, **f) -> int:
    with conn() as c:
        cur = c.execute(
            """INSERT INTO thinking_sessions
               (user_id, question, frame, answer, framework, action, scores, feedback)
               VALUES (?,?,?,?,?,?,?,?)""",
            (user_id, f.get("question"), f.get("frame"), f.get("answer"),
             f.get("framework"), f.get("action"),
             json.dumps(f.get("scores", {}), ensure_ascii=False), f.get("feedback")),
        )
        return cur.lastrowid


def sessions(user_id: int, limit: int = 50) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM thinking_sessions WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["scores"] = json.loads(d["scores"] or "{}")
        out.append(d)
    return out


# ---- principles (wisdom) ----
def add_principle(user_id: int, principle: str, source: str = "") -> None:
    with conn() as c:
        c.execute("INSERT INTO principles (user_id, principle, source) VALUES (?,?,?)",
                  (user_id, principle, source))


def principles(user_id: int) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM principles WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()]


# ---- knowledge ----
def add_knowledge(user_id: int, concept: str, relation: str = "", note: str = "") -> None:
    with conn() as c:
        c.execute("INSERT INTO knowledge_nodes (user_id, concept, relation, note) VALUES (?,?,?,?)",
                  (user_id, concept, relation, note))


def knowledge(user_id: int) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM knowledge_nodes WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()]


# ---- actions (feedback loop) ----
def add_action(user_id: int, problem: str, text: str) -> int:
    with conn() as c:
        return c.execute("INSERT INTO actions (user_id, problem, text) VALUES (?,?,?)",
                         (user_id, problem, text)).lastrowid


def actions(user_id: int, status: str | None = None) -> list[dict]:
    q = "SELECT * FROM actions WHERE user_id=?"
    args: list = [user_id]
    if status:
        q += " AND status=?"
        args.append(status)
    with conn() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY id DESC", args).fetchall()]


def resolve_action(action_id: int, status: str, result: str, lesson: str) -> dict | None:
    with conn() as c:
        c.execute("UPDATE actions SET status=?, result=?, lesson=? WHERE id=?",
                  (status, result, lesson, action_id))
        row = c.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
    return dict(row) if row else None

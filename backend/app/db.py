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
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
        # seed a demo user so the MVP is usable immediately
        if not c.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            c.execute("INSERT INTO users (name) VALUES (?)", ("demo",))


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

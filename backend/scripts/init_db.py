"""初始化 SQLite 数据库。

结构依据：开发文档/数据库设计.md v1.2
数据库文件：backend/travel.db（可用 --db 指定）

用法（在 backend/ 目录执行）：
    uv run python scripts/init_db.py
    uv run python scripts/init_db.py --copy-from travel.db   # 从旧库迁移数据
"""

import argparse
import sqlite3
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover
    pass

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = BASE_DIR / "travel.db"

# 建表顺序：invite_codes → users → travel_records（外键依赖）
SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS invite_codes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       VARCHAR(20)  NOT NULL UNIQUE,
    note       VARCHAR(50),
    max_uses   INTEGER      NOT NULL DEFAULT 1 CHECK (max_uses >= 1),
    used_count INTEGER      NOT NULL DEFAULT 0 CHECK (used_count >= 0),
    expires_at DATETIME,
    enabled    BOOLEAN      NOT NULL DEFAULT 1,
    created_at DATETIME     NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    username           VARCHAR(20)  NOT NULL,
    email              VARCHAR(100) NOT NULL,
    password_hash      VARCHAR(100) NOT NULL,
    failed_login_count INTEGER      NOT NULL DEFAULT 0,
    locked_until       DATETIME,
    created_at         DATETIME     NOT NULL,
    last_login_at      DATETIME,
    invite_code_id     INTEGER      REFERENCES invite_codes(id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uk_users_username ON users(username COLLATE NOCASE);
CREATE UNIQUE INDEX IF NOT EXISTS uk_users_email    ON users(email    COLLATE NOCASE);
CREATE INDEX        IF NOT EXISTS idx_users_invite  ON users(invite_code_id);

CREATE TABLE IF NOT EXISTS travel_records (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title             VARCHAR(100) NOT NULL,
    summary           VARCHAR(100) NOT NULL,
    departure         VARCHAR(50),
    destination       VARCHAR(50)  NOT NULL,
    days              INTEGER      NOT NULL CHECK (days BETWEEN 1 AND 15),
    start_date        DATE,
    people            INTEGER      NOT NULL CHECK (people BETWEEN 1 AND 20),
    budget_per_person INTEGER      NOT NULL CHECK (budget_per_person >= 1),
    interest_tags     TEXT,
    pace              VARCHAR(10),
    transport_pref    VARCHAR(20),
    hotel_pref        VARCHAR(20),
    special_needs     VARCHAR(200),
    used_guide        BOOLEAN      NOT NULL DEFAULT 0,
    guide_sources     TEXT,
    plan_content      TEXT         NOT NULL,
    created_at        DATETIME     NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_travel_records_user_time
    ON travel_records(user_id, created_at DESC);
"""

# 迁移时显式指定列，避免源库列顺序变化导致错位
COPY_TABLES = [
    (
        "invite_codes",
        ["id", "code", "note", "max_uses", "used_count", "expires_at", "enabled", "created_at"],
    ),
    (
        "users",
        ["id", "username", "email", "password_hash", "failed_login_count",
         "locked_until", "created_at", "last_login_at", "invite_code_id"],
    ),
    (
        "travel_records",
        ["id", "user_id", "title", "summary", "departure", "destination", "days",
         "start_date", "people", "budget_per_person", "interest_tags", "pace",
         "transport_pref", "hotel_pref", "special_needs", "used_guide",
         "guide_sources", "plan_content", "created_at"],
    ),
]


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def copy_data(conn: sqlite3.Connection, source: Path) -> None:
    if not source.exists():
        print(f"[跳过] 源数据库不存在：{source}")
        return

    conn.execute("ATTACH DATABASE ? AS old", (str(source),))
    try:
        for table, columns in COPY_TABLES:
            column_text = ", ".join(columns)
            source_count = conn.execute(f"SELECT COUNT(*) FROM old.{table}").fetchone()[0]
            conn.execute(
                f"INSERT OR IGNORE INTO {table} ({column_text}) "
                f"SELECT {column_text} FROM old.{table}"
            )
            target_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: 源 {source_count} 条 → 目标共 {target_count} 条")
        conn.commit()
    finally:
        conn.execute("DETACH DATABASE old")


def print_summary(conn: sqlite3.Connection) -> None:
    print("\n表结构：")
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()

    for (table,) in tables:
        columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"\n  {table}（{len(columns)} 列，{row_count} 行）")
        for col in columns:
            col_id, name, col_type, notnull, default, pk = col
            flags = []
            if pk:
                flags.append("PK")
            if notnull:
                flags.append("NOT NULL")
            if default is not None:
                flags.append(f"DEFAULT {default}")
            print(f"    - {name:<20} {col_type:<12} {' '.join(flags)}")

    print("\n索引：")
    for (table,) in tables:
        for index in conn.execute(f"PRAGMA index_list({table})").fetchall():
            index_name = index[1]
            unique = "唯一" if index[2] else "普通"
            print(f"    - {index_name:<32} ({table}, {unique})")


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化 SQLite 数据库")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="数据库文件路径")
    parser.add_argument("--copy-from", default=None, help="从指定旧数据库迁移数据")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    existed = db_path.exists()
    conn = sqlite3.connect(db_path)
    try:
        create_schema(conn)
        print(f"[{'已存在，校验结构' if existed else '新建'}] {db_path}")

        if args.copy_from:
            print("\n迁移数据：")
            copy_data(conn, Path(args.copy_from).resolve())

        print_summary(conn)
    finally:
        conn.close()

    print(f"\n完成：{db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

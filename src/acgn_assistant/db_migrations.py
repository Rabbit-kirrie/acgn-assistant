from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class _ColumnSpec:
    name: str
    sql_type: str


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"), {"name": table_name}
    ).fetchone()
    return row is not None


def _existing_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {r[1] for r in rows}  # name


def _index_exists(conn, index_name: str) -> bool:
    row = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='index' AND name=:name"), {"name": index_name}
    ).fetchone()
    return row is not None


def _add_column_if_missing(conn, *, table: str, col: _ColumnSpec) -> None:
    cols = _existing_columns(conn, table)
    if col.name in cols:
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col.name} {col.sql_type}"))


def _create_index_if_missing(conn, *, index_name: str, table: str, column: str) -> None:
    if _index_exists(conn, index_name):
        return
    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({column})"))


def apply_sqlite_migrations(engine: Engine) -> None:
    """Apply lightweight SQLite migrations for existing DB files.

    Notes:
    - This is intentionally minimal: only ADD COLUMN / CREATE INDEX.
    - It keeps backward compatibility for users who already have app.db.
    """

    # Table names are SQLModel defaults (lowercase class names in this project)
    migrations: dict[str, list[_ColumnSpec]] = {
        # User
        "user": [
            _ColumnSpec("is_active", "BOOLEAN DEFAULT 1"),
        ],
        # Conversation
        "conversation": [
            _ColumnSpec("updated_at", "TIMESTAMP"),
            _ColumnSpec("deleted_at", "TIMESTAMP"),
        ],
        # Message
        "message": [
            _ColumnSpec("deleted_at", "TIMESTAMP"),
        ],
        # DiaryEntry
        "diaryentry": [
            _ColumnSpec("deleted_at", "TIMESTAMP"),
        ],
        # EmotionRecord
        "emotionrecord": [
            _ColumnSpec("deleted_at", "TIMESTAMP"),
        ],
        # AssessmentSubmission
        "assessmentsubmission": [
            _ColumnSpec("deleted_at", "TIMESTAMP"),
        ],
        # TrainingLog
        "traininglog": [
            _ColumnSpec("deleted_at", "TIMESTAMP"),
        ],
        # MonthlyReport
        "monthlyreport": [
            _ColumnSpec("deleted_at", "TIMESTAMP"),
        ],
        # Resource / EmergencyContact / MemoryItem were introduced with deleted_at already,
        # but keep them here in case someone created DB before those fields existed.
        "resource": [
            _ColumnSpec("deleted_at", "TIMESTAMP"),
        ],
        "emergencycontact": [
            _ColumnSpec("deleted_at", "TIMESTAMP"),
        ],
        "memoryitem": [
            _ColumnSpec("deleted_at", "TIMESTAMP"),
        ],

        # GuestbookMessage
        "guestbookmessage": [
            _ColumnSpec("parent_id", "TEXT"),
        ],
    }

    # Indexes to back soft-delete filters
    deleted_at_indexes: list[tuple[str, str, str]] = [
        ("ix_conversation_deleted_at", "conversation", "deleted_at"),
        ("ix_message_deleted_at", "message", "deleted_at"),
        ("ix_diaryentry_deleted_at", "diaryentry", "deleted_at"),
        ("ix_emotionrecord_deleted_at", "emotionrecord", "deleted_at"),
        ("ix_assessmentsubmission_deleted_at", "assessmentsubmission", "deleted_at"),
        ("ix_traininglog_deleted_at", "traininglog", "deleted_at"),
        ("ix_monthlyreport_deleted_at", "monthlyreport", "deleted_at"),
        ("ix_resource_deleted_at", "resource", "deleted_at"),
        ("ix_emergencycontact_deleted_at", "emergencycontact", "deleted_at"),
        ("ix_memoryitem_deleted_at", "memoryitem", "deleted_at"),
    ]

    extra_indexes: list[tuple[str, str, str]] = [
        ("ix_user_is_active", "user", "is_active"),
        ("ix_guestbookmessage_parent_id", "guestbookmessage", "parent_id"),
    ]

    with engine.begin() as conn:
        # Only apply to SQLite
        conn.execute(text("PRAGMA foreign_keys=ON"))

        for table, cols in migrations.items():
            if not _table_exists(conn, table):
                continue
            for col in cols:
                _add_column_if_missing(conn, table=table, col=col)

        for index_name, table, column in deleted_at_indexes:
            if not _table_exists(conn, table):
                continue
            _create_index_if_missing(conn, index_name=index_name, table=table, column=column)

        for index_name, table, column in extra_indexes:
            if not _table_exists(conn, table):
                continue
            _create_index_if_missing(conn, index_name=index_name, table=table, column=column)

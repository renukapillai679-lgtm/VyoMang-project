"""Database connection (SQLite + SQLAlchemy). The file vyomang.db is created automatically."""
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_PATH = Path(__file__).resolve().parent / "vyomang.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: one database session per request, always closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _upgrade_old_users_table():
    """Databases made by the first version have a simpler users table.
    Rebuild it with the new columns (full_name, picture_url, google_id, created_at) and keep every user."""
    from models import User  # imported here to avoid a circular import

    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    if {"google_id", "created_at"} <= cols:
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE users RENAME TO users_old"))
    User.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, email, salt, pw_hash, created_at) "
            "SELECT id, email, salt, pw_hash, replace(created, 'T', ' ') FROM users_old"))
        conn.execute(text("DROP TABLE users_old"))
        conn.execute(text("DROP TABLE IF EXISTS sessions"))  # login now uses JWT tokens instead


def init_db():
    import models  # noqa: F401  (registers the tables)
    from seed import seed_if_empty

    _upgrade_old_users_table()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_if_empty(db)

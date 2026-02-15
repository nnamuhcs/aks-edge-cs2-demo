from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings


def _prepare_sqlite_dir(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    db_path = database_url.replace("sqlite:///", "", 1)
    if db_path == ":memory:":
        return
    Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


_prepare_sqlite_dir(settings.database_url)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def ensure_schema_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    migrations = {
        "skins": {
            "image_url": "ALTER TABLE skins ADD COLUMN image_url VARCHAR(1024)",
            "listing_url": "ALTER TABLE skins ADD COLUMN listing_url VARCHAR(1024)",
            "thesis": "ALTER TABLE skins ADD COLUMN thesis VARCHAR(512)",
        },
        "price_snapshots": {
            "source": "ALTER TABLE price_snapshots ADD COLUMN source VARCHAR(64) DEFAULT 'unknown' NOT NULL",
            "source_ref": "ALTER TABLE price_snapshots ADD COLUMN source_ref VARCHAR(1024)",
        },
    }

    with engine.begin() as conn:
        for table, table_migrations in migrations.items():
            existing = {
                row[1]
                for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            }
            for col, ddl in table_migrations.items():
                if col not in existing:
                    conn.execute(text(ddl))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

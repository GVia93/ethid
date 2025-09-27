from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.config import settings


class Base(DeclarativeBase):
    """База ORM-моделей."""


_engine = None
SessionLocal: sessionmaker | None = None


def init_engine(url: str | None = None) -> None:
    global _engine, SessionLocal
    url = url or settings.DATABASE_URL
    assert url, "DATABASE_URL is required"
    _engine = create_engine(
        url,
        pool_size=getattr(settings, "DB_POOL_SIZE", 5),
        max_overflow=getattr(settings, "DB_MAX_OVERFLOW", 10),
        echo=getattr(settings, "DB_ECHO", False),
        pool_pre_ping=True,
    )
    SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def create_all() -> None:
    assert _engine is not None, "Call init_engine() first"
    Base.metadata.create_all(_engine)

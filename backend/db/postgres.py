"""PostgreSQL / Supabase Async Database Connection & Session Management."""

import os
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

log = logging.getLogger(__name__)

Base = declarative_base()

_engine = None
_AsyncSessionLocal = None


def is_cloud_allowed() -> bool:
    """Return True only when running on GitHub Actions, Production, or explicitly permitted."""
    is_github = os.environ.get("GITHUB_ACTIONS", "").lower() == "true" or os.environ.get("CI", "").lower() == "true"
    env = os.environ.get("ENVIRONMENT", "development").lower()
    allow_dev = os.environ.get("ALLOW_CLOUD_IN_DEV", "").lower() == "true"
    return is_github or env == "production" or allow_dev


def get_database_url() -> str:
    """Retrieve normalized async database connection URL."""
    url = (
        os.environ.get("POSTGRES_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("SUPABASE_DB_URL")
        or ""
    ).strip()

    # Guard: dev servers must not connect to remote cloud Supabase / Postgres.
    # Cloud Supabase is strictly used when pushed to GitHub / Production.
    if any(cloud in url for cloud in [".supabase.co", "pooler.supabase.com"]):
        if not is_cloud_allowed():
            log.info("Local development mode active: bypassing remote Supabase cloud DB; using local database.")
            url = ""

    if not url:
        # Fallback to local async sqlite file for seamless offline local dev/testing
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "financial_erp.db"))
        return f"sqlite+aiosqlite:///{db_path}"

    # Supabase / Heroku / Render provide postgres:// or postgresql://
    # asyncpg requires postgresql+asyncpg://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return url


def get_engine():
    """Get or initialize the SQLAlchemy async engine."""
    global _engine
    if _engine is None:
        db_url = get_database_url()
        is_sqlite = db_url.startswith("sqlite")

        engine_kwargs = {"echo": False}
        if is_sqlite:
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            engine_kwargs.update(
                {
                    "pool_size": int(os.environ.get("PG_POOL_SIZE", "10")),
                    "max_overflow": int(os.environ.get("PG_MAX_OVERFLOW", "20")),
                    "pool_pre_ping": True,
                }
            )

        _engine = create_async_engine(db_url, **engine_kwargs)
        log.info("Initialized financial database engine with dialect: %s", _engine.dialect.name)
    return _engine


def get_session_factory():
    """Get or initialize the async sessionmaker."""
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        engine = get_engine()
        _AsyncSessionLocal = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _AsyncSessionLocal


async def get_pg_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session with automatic cleanup."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_postgres_db():
    """Create financial tables if they don't exist yet."""
    engine = get_engine()
    # Import all models to ensure they are attached to Base.metadata
    import models.sql_financials  # noqa: F401

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("Financial core schema successfully synchronized on %s.", engine.dialect.name)
    except Exception as e:
        log.warning("PostgreSQL connection failed (%s); falling back to local SQLite engine.", e)
        global _engine, _AsyncSessionLocal
        if _engine is not None:
            await _engine.dispose()
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "financial_erp.db"))
        fallback_url = f"sqlite+aiosqlite:///{db_path}"
        _engine = create_async_engine(fallback_url, connect_args={"check_same_thread": False})
        _AsyncSessionLocal = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("Financial core schema initialized on local SQLite fallback: %s", fallback_url)


async def close_postgres_db():
    """Dispose the SQLAlchemy engine pool."""
    global _engine, _AsyncSessionLocal
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _AsyncSessionLocal = None
        log.info("Financial database engine disposed.")

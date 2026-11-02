"""
AIORI Database Session Management
Async SQLAlchemy engine and session factory for SQLite.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import event

from config import settings, BASE_DIR
from database.models import Base


# Resolve the database path relative to the backend directory
_db_path = BASE_DIR / "database" / "aiori.db"
_db_url = f"sqlite+aiosqlite:///{_db_path}"

engine = create_async_engine(
    _db_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Create all tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """FastAPI dependency: yield an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def shutdown_db():
    """Dispose the engine on application shutdown."""
    await engine.dispose()

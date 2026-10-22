"""Database engine and session setup."""

from config import get_settings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

settings = get_settings()

# Convert postgresql:// to postgresql+asyncpg:// for async support
database_url = settings.database_url
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
# asyncpg uses ssl= not sslmode= (sslmode is a libpq param that asyncpg
# only understands in DSN parsing, not as a keyword arg from SQLAlchemy)
database_url = database_url.replace("sslmode=", "ssl=")

engine = create_async_engine(
    database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

async_session = async_sessionmaker(engine, expire_on_commit=False)

Base = declarative_base()

# NOTE: schema DDL is owned solely by the SQL migrations (db/migrations.py) —
# the single provisioning path. Do NOT add Base.metadata.create_all here: a
# second, model-derived schema source is exactly what let dev and prod diverge
# (e.g. a CHECK constraint present in migrations but absent from the models).
# `Base` stays for ORM mapping only.


async def get_db():
    """Dependency for FastAPI routes."""
    async with async_session() as session:
        yield session

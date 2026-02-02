import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

# Use environment variable for database URL, defaulting to SQLite for development
SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./test.db")

# Configure engine based on database type
connect_args = {}
engine_kwargs = {}

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    # SQLite uses StaticPool for thread safety in multi-threaded environments
    # For in-memory SQLite, use StaticPool to share connection across threads
    if ":memory:" in SQLALCHEMY_DATABASE_URL:
        engine_kwargs["poolclass"] = StaticPool
else:
    # PostgreSQL/MySQL connection pool settings for production
    engine_kwargs.update({
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "10")),
        "pool_pre_ping": True,  # Enable connection health checks
        "pool_recycle": 3600,  # Recycle connections after 1 hour
    })

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

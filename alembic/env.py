import os
import sys
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
from models.base import Base

load_dotenv()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override sqlalchemy.url from environment variable if set
url = os.getenv("DATABASE_URL")
if url:
    # Alembic runs synchronously, so convert asyncpg URL to psycopg2-compatible
    url = url.replace("+asyncpg", "")
    # asyncpg uses ssl=require, psycopg2 uses sslmode=require
    url = url.replace("ssl=require", "sslmode=require")
    config.set_main_option("sqlalchemy.url", url)

# Safety check: confirm before running migrations against non-local databases
effective_url = config.get_main_option("sqlalchemy.url") or ""
if "localhost" not in effective_url:
    response = input(f"You are running migrations against non-dev DB url {effective_url}. Is this your intention? (Y/N) ")
    if response.strip().lower() != "y":
        sys.exit(1)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

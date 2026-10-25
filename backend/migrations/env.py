from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401 -- registers tables with Base.metadata
from app.core.config import get_settings
from app.core.db import Base

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    url = get_settings().database_url
    engine = create_engine(
        url,
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": 10} if url.startswith("postgresql") else {},
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

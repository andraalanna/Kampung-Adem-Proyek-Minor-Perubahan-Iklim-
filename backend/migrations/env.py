from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Objects managed by PostGIS/TimescaleDB, not by our models.
_IGNORE_TABLES = {"spatial_ref_sys"}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and (name in _IGNORE_TABLES or (name or "").startswith("readings_")):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(url=get_settings().database_url, target_metadata=target_metadata,
                      literal_binds=True, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""Database connection and initial reference catalog for the AQUAVERSE local MVP."""

from collections.abc import Generator
from functools import lru_cache
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


DEFAULT_DB_FILE = Path(__file__).resolve().parents[1] / "data" / "aquaverse.sqlite3"


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = os.getenv("AQUAVERSE_DATABASE_URL")
    if not url:
        DEFAULT_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{DEFAULT_DB_FILE}"

    connect_args = {"check_same_thread": False} if url.startswith("sqlite:") else {}
    engine = create_engine(url, connect_args=connect_args)

    if url.startswith("sqlite:"):
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _connection_record):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_db() -> Generator[Session, None, None]:
    session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with session_factory() as session:
        yield session


def init_database() -> None:
    # Import model declarations before create_all so SQLAlchemy sees the tables.
    from . import models  # Import Phase 1C models.
    from . import decision_models  # Import Phase 2A additive tables.
    from . import outcome_models  # Import Phase 2B outcome comparison tables.
    from . import connect_models  # Additive AquaConnect tables.
    from . import auth_models  # Additive auth and ownership tables; legacy rows remain unchanged.
    from .models import CultureSystem, Species

    Base.metadata.create_all(bind=get_engine())
    session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with session_factory() as session:
        if session.get(Species, "monopterus_albus") is None:
            session.add(Species(
                id="monopterus_albus",
                scientific_name="Monopterus albus",
                common_name_vi="Lươn đồng",
                status="pilot",
            ))
        if session.get(CultureSystem, "mudfree_tank") is None:
            session.add(CultureSystem(
                id="mudfree_tank",
                name_vi="Bể nuôi không bùn",
                description="Cấu hình thí điểm: lươn đồng nuôi không bùn trong bể.",
            ))
        session.commit()

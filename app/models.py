from __future__ import annotations

import os
from uuid import uuid4

from sqlalchemy import JSON, Boolean, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg://battleship:battleship@localhost:5432/battleship")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Game(Base):
    __tablename__ = "games"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    ships: Mapped[list] = mapped_column(JSON)
    received_shots: Mapped[list] = mapped_column(JSON, default=list)
    own_shots: Mapped[dict] = mapped_column(JSON, default=dict)
    pending_shot: Mapped[str | None] = mapped_column(String(3), nullable=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False)

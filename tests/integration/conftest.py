import os

# Должен быть установлен ДО импорта app.main/app.models,
# потому что engine создаётся при импорте моделей.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://battleship:battleship@postgres:5432/battleship_test",
)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.main import app
from app.models import Game, SessionLocal


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def clean_database():
    db = SessionLocal()

    try:
        db.execute(delete(Game))
        db.commit()
        yield
    finally:
        db.close()


@pytest.fixture
def db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
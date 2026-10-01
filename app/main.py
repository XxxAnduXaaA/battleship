from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from .game import RESULTS, next_shot, shot_result, standard_ships, validate_ships
from .models import Base, Game, SessionLocal, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="Battleship service", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, error: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": error.errors()[0]["msg"]})


class Ship(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coordinates: list[str]


class StartResponse(BaseModel):
    session_id: UUID
    ships: list[Ship]


class CoordinateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coordinate: str


class CoordinateRequest(CoordinateResponse):
    pass


class ResultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: str = Field(pattern="^(miss|hit|killed)$")


class ResultResponse(ResultRequest):
    pass


class StatusResponse(BaseModel):
    status: str


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_game(session_id: str, db: Session) -> Game:
    game = db.get(Game, session_id)
    if not game:
        raise HTTPException(404, "Game session not found")
    if game.closed:
        raise HTTPException(410, "Game session is closed")
    return game


@app.post("/game", response_model=StartResponse, status_code=201)
def start_game(db: Session = Depends(db_session)):
    ships = standard_ships()
    validate_ships(ships)
    game = Game(ships=ships, received_shots=[], own_shots={})
    db.add(game)
    db.commit()
    return {"session_id": game.session_id, "ships": ships}


@app.post("/game/{session_id}/shot", response_model=CoordinateResponse)
def make_shot(session_id: str, db: Session = Depends(db_session)):
    game = get_game(session_id, db)
    if game.pending_shot:
        raise HTTPException(409, "Previous shot result has not been received")
    try:
        target = next_shot(game.own_shots)
    except StopIteration:
        raise HTTPException(409, "No available cells remain")
    game.pending_shot = target
    db.commit()
    return {"coordinate": target}


@app.post("/game/{session_id}/shot/result", response_model=StatusResponse)
def accept_result(session_id: str, body: ResultRequest, db: Session = Depends(db_session)):
    game = get_game(session_id, db)
    if not game.pending_shot:
        raise HTTPException(409, "No shot is awaiting a result")
    own_shots = dict(game.own_shots)
    own_shots[game.pending_shot] = body.result
    game.own_shots = own_shots
    game.pending_shot = None
    db.commit()
    return {"status": "accepted"}


@app.post("/game/{session_id}/opponent-shot", response_model=ResultResponse)
def opponent_shot(session_id: str, body: CoordinateRequest, db: Session = Depends(db_session)):
    game = get_game(session_id, db)
    try:
        from .game import parse_coordinate
        parse_coordinate(body.coordinate)
    except ValueError as error:
        raise HTTPException(400, str(error))
    received = set(game.received_shots)
    if body.coordinate in received:
        raise HTTPException(400, "Coordinate has already been shot")
    received.add(body.coordinate)
    game.received_shots = sorted(received)
    result = shot_result(game.ships, received, body.coordinate)
    db.commit()
    return {"result": result}


@app.post("/game/{session_id}/close", response_model=StatusResponse)
def close_game(session_id: str, db: Session = Depends(db_session)):
    game = db.get(Game, session_id)
    if not game:
        raise HTTPException(404, "Game session not found")
    if game.closed:
        raise HTTPException(400, "Game session is already closed")
    game.closed = True
    db.commit()
    return {"status": "closed"}

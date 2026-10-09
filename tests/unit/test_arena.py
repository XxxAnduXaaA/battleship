import asyncio
import json
import uuid
from typing import Callable

import httpx

from app.game import next_shot, shot_result, standard_ships
from arena.main import Arena, Player


class FakeService:
    """In-memory stand-in for one battleship service instance, driven over httpx.MockTransport."""

    def __init__(self, ships=None, misbehave: dict[str, Callable] | None = None):
        self.ships = ships if ships is not None else standard_ships()
        self.own_shots: dict[str, str] = {}
        self.received: set[str] = set()
        self.pending: str | None = None
        self.closed = False
        self.misbehave = misbehave or {}
        self.session_id = str(uuid.uuid4())

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path

        if path == "/game":
            return httpx.Response(201, json={"session_id": self.session_id, "ships": self.ships})

        if path.endswith("/shot/result"):
            if "shot_result" in self.misbehave:
                return self.misbehave["shot_result"](self, request)
            body = json.loads(request.content)
            self.own_shots[self.pending] = body["result"]
            self.pending = None
            return httpx.Response(200, json={"status": "accepted"})

        if path.endswith("/shot"):
            if "shot" in self.misbehave:
                return self.misbehave["shot"](self, request)
            target = next_shot(self.own_shots)
            self.pending = target
            return httpx.Response(200, json={"coordinate": target})

        if path.endswith("/opponent-shot"):
            body = json.loads(request.content)
            coordinate = body["coordinate"]
            if "opponent_shot" in self.misbehave:
                return self.misbehave["opponent_shot"](self, coordinate)
            self.received.add(coordinate)
            result = shot_result(self.ships, self.received, coordinate)
            return httpx.Response(200, json={"result": result})

        if path.endswith("/close"):
            self.closed = True
            return httpx.Response(200, json={"status": "closed"})

        return httpx.Response(404, json={"detail": "not found"})


def build_arena(services: dict[str, FakeService], timeout: float = 1.0) -> Arena:
    def handler(request: httpx.Request) -> httpx.Response:
        return services[request.url.host].handle(request)

    arena = Arena(Player("alpha", "http://alpha"), Player("beta", "http://beta"))
    arena.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout)
    return arena


def test_honest_match_ends_cleanly_and_closes_both_sessions():
    services = {"alpha": FakeService(), "beta": FakeService()}
    arena = build_arena(services)

    result = asyncio.run(arena.play())

    assert result.technical is False
    assert result.winner in ("alpha", "beta")
    assert result.loser in ("alpha", "beta")
    assert result.winner != result.loser
    assert services["alpha"].closed
    assert services["beta"].closed


def test_lying_defender_is_caught_as_technical_defeat(monkeypatch):
    # Force alpha to attack first, so the very first exchange is alpha -> beta (the liar) defending,
    # instead of leaving it to a 50/50 coin flip whether beta ever gets to defend before the match ends.
    monkeypatch.setattr("arena.main.random.randrange", lambda _: 0)

    def always_lie(service: FakeService, coordinate: str) -> httpx.Response:
        service.received.add(coordinate)
        truth = shot_result(service.ships, service.received, coordinate)
        lie = "hit" if truth == "miss" else "miss"
        return httpx.Response(200, json={"result": lie})

    services = {"alpha": FakeService(), "beta": FakeService(misbehave={"opponent_shot": always_lie})}
    arena = build_arena(services)

    result = asyncio.run(arena.play())

    assert result.technical is True
    assert result.loser == "beta"
    assert result.winner == "alpha"


def test_timeout_is_a_technical_defeat_for_the_slow_player(monkeypatch):
    # Force beta to attack first, so its misbehaving /shot fires on the very first call instead of
    # leaving it to chance whether alpha wins outright before beta ever gets a turn.
    monkeypatch.setattr("arena.main.random.randrange", lambda _: 1)

    def never_respond(service: FakeService, request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("too slow")

    services = {"alpha": FakeService(), "beta": FakeService(misbehave={"shot": never_respond})}
    arena = build_arena(services)

    result = asyncio.run(arena.play())

    assert result.technical is True
    assert result.loser == "beta"


def test_invalid_json_body_is_a_technical_defeat(monkeypatch):
    monkeypatch.setattr("arena.main.random.randrange", lambda _: 1)

    def bad_json(service: FakeService, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    services = {"alpha": FakeService(), "beta": FakeService(misbehave={"shot": bad_json})}
    arena = build_arena(services)

    result = asyncio.run(arena.play())

    assert result.technical is True
    assert result.loser == "beta"


def test_non_dict_json_body_is_a_technical_defeat(monkeypatch):
    monkeypatch.setattr("arena.main.random.randrange", lambda _: 1)

    def list_body(service: FakeService, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "a", "dict"])

    services = {"alpha": FakeService(), "beta": FakeService(misbehave={"shot": list_body})}
    arena = build_arena(services)

    result = asyncio.run(arena.play())

    assert result.technical is True
    assert result.loser == "beta"


def test_repeated_own_shot_is_a_technical_defeat(monkeypatch):
    monkeypatch.setattr("arena.main.random.randrange", lambda _: 1)
    first_shot = {"value": None}

    def repeat_shot(service: FakeService, request: httpx.Request) -> httpx.Response:
        if first_shot["value"] is None:
            target = next_shot(service.own_shots)
            first_shot["value"] = target
        else:
            target = first_shot["value"]
        service.pending = target
        return httpx.Response(200, json={"coordinate": target})

    services = {"alpha": FakeService(), "beta": FakeService(misbehave={"shot": repeat_shot})}
    arena = build_arena(services)

    result = asyncio.run(arena.play())

    assert result.technical is True
    assert result.loser == "beta"


def test_unexpected_http_status_is_a_technical_defeat(monkeypatch):
    monkeypatch.setattr("arena.main.random.randrange", lambda _: 1)

    def server_error(service: FakeService, request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    services = {"alpha": FakeService(), "beta": FakeService(misbehave={"shot": server_error})}
    arena = build_arena(services)

    result = asyncio.run(arena.play())

    assert result.technical is True
    assert result.loser == "beta"

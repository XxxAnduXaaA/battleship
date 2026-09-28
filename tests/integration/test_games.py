from uuid import UUID

import pytest

from app.game import ALL_COORDINATES
from app.models import Game


def create_game(client):
    response = client.post("/game")

    assert response.status_code == 201

    data = response.json()

    return data["session_id"], data["ships"]


def test_create_game(client, db):
    response = client.post("/game")

    assert response.status_code == 201

    data = response.json()

    # API вернул корректный session_id
    session_id = data["session_id"]
    UUID(session_id)

    # API вернул флот
    assert len(data["ships"]) == 10

    # Игра реально сохранилась в БД
    game = db.get(Game, session_id)

    assert game is not None
    assert game.session_id == session_id
    assert game.ships == data["ships"]

    assert game.received_shots == []
    assert game.own_shots == {}
    assert game.pending_shot is None
    assert game.closed is False


def test_get_shot(client, db):
    session_id, _ = create_game(client)

    response = client.post(
        f"/game/{session_id}/shot"
    )

    assert response.status_code == 200

    coordinate = response.json()["coordinate"]

    # Проверяем, что pending_shot сохранился в БД
    game = db.get(Game, session_id)

    assert game.pending_shot == coordinate


def test_cannot_get_next_shot_before_result(client):
    session_id, _ = create_game(client)

    first_response = client.post(
        f"/game/{session_id}/shot"
    )

    assert first_response.status_code == 200

    second_response = client.post(
        f"/game/{session_id}/shot"
    )

    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "Previous shot result has not been received"
    )


def test_submit_shot_result(client, db):
    session_id, _ = create_game(client)

    shot_response = client.post(
        f"/game/{session_id}/shot"
    )

    assert shot_response.status_code == 200

    coordinate = shot_response.json()["coordinate"]

    result_response = client.post(
        f"/game/{session_id}/shot/result",
        json={
            "result": "miss"
        },
    )

    assert result_response.status_code == 200
    assert result_response.json() == {
        "status": "accepted"
    }

    # Проверяем изменения в БД
    game = db.get(Game, session_id)

    assert game.pending_shot is None
    assert game.own_shots == {
        coordinate: "miss"
    }


def test_cannot_submit_result_without_shot(client):
    session_id, _ = create_game(client)

    response = client.post(
        f"/game/{session_id}/shot/result",
        json={
            "result": "miss"
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "No shot is awaiting a result"


def test_opponent_shot_miss(client, db):
    session_id, ships = create_game(client)

    occupied = {cell for ship in ships for cell in ship["coordinates"]}
    target = next(coord for coord in ALL_COORDINATES if coord not in occupied)

    response = client.post(
        f"/game/{session_id}/opponent-shot",
        json={
            "coordinate": target
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "result": "miss"
    }

    game = db.get(Game, session_id)

    assert game.received_shots == [target]


def test_opponent_shot_hit(client, db):
    session_id, ships = create_game(client)

    # Берём клетку корабля длиннее одной палубы, чтобы один выстрел давал "hit", а не "killed".
    target = next(ship for ship in ships if len(ship["coordinates"]) > 1)["coordinates"][0]

    response = client.post(
        f"/game/{session_id}/opponent-shot",
        json={
            "coordinate": target
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "result": "hit"
    }

    game = db.get(Game, session_id)

    assert game.received_shots == [target]


def test_opponent_shot_killed(client):
    session_id, ships = create_game(client)

    # Расстановка случайная (standard_ships), поэтому берём реальные клетки самого длинного корабля.
    target_ship = max(ships, key=lambda ship: len(ship["coordinates"]))
    coordinates = target_ship["coordinates"]

    for coordinate in coordinates[:-1]:
        response = client.post(
            f"/game/{session_id}/opponent-shot",
            json={
                "coordinate": coordinate
            },
        )

        assert response.status_code == 200
        assert response.json()["result"] == "hit"

    response = client.post(
        f"/game/{session_id}/opponent-shot",
        json={
            "coordinate": coordinates[-1]
        },
    )

    assert response.status_code == 200
    assert response.json()["result"] == "killed"


def test_cannot_shoot_same_coordinate_twice(client):
    session_id, _ = create_game(client)

    first_response = client.post(
        f"/game/{session_id}/opponent-shot",
        json={
            "coordinate": "J10"
        },
    )

    assert first_response.status_code == 200

    second_response = client.post(
        f"/game/{session_id}/opponent-shot",
        json={
            "coordinate": "J10"
        },
    )

    assert second_response.status_code == 400


def test_game_not_found(client):
    session_id = "00000000-0000-0000-0000-000000000000"

    response = client.post(
        f"/game/{session_id}/shot"
    )

    assert response.status_code == 404


def test_shot_result_game_not_found(client):
    session_id = "00000000-0000-0000-0000-000000000000"

    response = client.post(
        f"/game/{session_id}/shot/result",
        json={
            "result": "miss"
        },
    )

    assert response.status_code == 404


def test_opponent_shot_game_not_found(client):
    session_id = "00000000-0000-0000-0000-000000000000"

    response = client.post(
        f"/game/{session_id}/opponent-shot",
        json={
            "coordinate": "J10"
        },
    )

    assert response.status_code == 404


def test_close_game_not_found(client):
    session_id = "00000000-0000-0000-0000-000000000000"

    response = client.post(
        f"/game/{session_id}/close"
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "coordinate",
    [
        "A0",
        "A11",
        "K1",
        "Z99",
        "",
        "AA1",
        "1A",
    ],
)
def test_invalid_opponent_shot_coordinate(client, coordinate):
    session_id, _ = create_game(client)

    response = client.post(
        f"/game/{session_id}/opponent-shot",
        json={
            "coordinate": coordinate
        },
    )

    assert response.status_code == 400


def test_invalid_shot_result(client):
    session_id, _ = create_game(client)

    shot_response = client.post(
        f"/game/{session_id}/shot"
    )

    assert shot_response.status_code == 200

    response = client.post(
        f"/game/{session_id}/shot/result",
        json={
            "result": "destroyed"
        },
    )

    assert response.status_code == 400


def test_close_game(client, db):
    session_id, _ = create_game(client)

    response = client.post(
        f"/game/{session_id}/close"
    )

    assert response.status_code == 200

    game = db.get(Game, session_id)

    assert game.closed is True


def test_cannot_close_game_twice(client):
    session_id, _ = create_game(client)

    first_response = client.post(
        f"/game/{session_id}/close"
    )

    assert first_response.status_code == 200

    second_response = client.post(
        f"/game/{session_id}/close"
    )

    assert second_response.status_code == 400


def test_cannot_get_shot_after_game_closed(client):
    session_id, _ = create_game(client)

    close_response = client.post(
        f"/game/{session_id}/close"
    )

    assert close_response.status_code == 200

    response = client.post(
        f"/game/{session_id}/shot"
    )

    assert response.status_code == 410


def test_cannot_submit_result_after_game_closed(client):
    session_id, _ = create_game(client)

    close_response = client.post(
        f"/game/{session_id}/close"
    )

    assert close_response.status_code == 200

    response = client.post(
        f"/game/{session_id}/shot/result",
        json={
            "result": "miss"
        },
    )

    assert response.status_code == 410


def test_cannot_receive_opponent_shot_after_game_closed(client):
    session_id, _ = create_game(client)

    close_response = client.post(
        f"/game/{session_id}/close"
    )

    assert close_response.status_code == 200

    response = client.post(
        f"/game/{session_id}/opponent-shot",
        json={
            "coordinate": "J10"
        },
    )

    assert response.status_code == 410
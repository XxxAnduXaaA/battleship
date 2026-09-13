from __future__ import annotations

import argparse
import asyncio
import random
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx

from app.game import RESULTS, parse_coordinate, shot_result, validate_ships

TIMEOUT_SECONDS = 1.0


class TechnicalDefeat(RuntimeError):
    def __init__(self, loser: str, reason: str):
        self.loser = loser
        self.reason = reason
        super().__init__(f"{loser}: {reason}")


@dataclass
class Player:
    name: str
    base_url: str
    session_id: str = ""
    ships: list[dict[str, list[str]]] = field(default_factory=list)
    shots: set[str] = field(default_factory=set)
    received: set[str] = field(default_factory=set)


class Arena:
    def __init__(self, first_url: str, second_url: str):
        self.players = [Player("player-1", first_url.rstrip("/")), Player("player-2", second_url.rstrip("/"))]
        self.client = httpx.AsyncClient(timeout=TIMEOUT_SECONDS)

    async def request(self, player: Player, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self.client.request(method, f"{player.base_url}{path}", **kwargs)
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise TechnicalDefeat(player.name, f"request failed or exceeded {TIMEOUT_SECONDS:g} second: {error}")
        if not 200 <= response.status_code < 300:
            raise TechnicalDefeat(player.name, f"unexpected HTTP {response.status_code}: {response.text[:200]}")
        try:
            payload = response.json()
        except ValueError:
            raise TechnicalDefeat(player.name, "response is not valid JSON")
        if not isinstance(payload, dict):
            raise TechnicalDefeat(player.name, "response JSON must be an object")
        return payload

    async def start(self, player: Player) -> None:
        body = await self.request(player, "POST", "/game")
        try:
            player.session_id = str(UUID(body["session_id"]))
            player.ships = body["ships"]
            validate_ships(player.ships)
        except (KeyError, TypeError, ValueError) as error:
            raise TechnicalDefeat(player.name, f"invalid starting position: {error}")

    async def get_shot(self, player: Player) -> str:
        body = await self.request(player, "POST", f"/game/{player.session_id}/shot")
        try:
            target = body["coordinate"]
            parse_coordinate(target)
        except (KeyError, ValueError) as error:
            raise TechnicalDefeat(player.name, f"invalid shot coordinate: {error}")
        if target in player.shots:
            raise TechnicalDefeat(player.name, f"repeated shot: {target}")
        player.shots.add(target)
        return target

    async def defend(self, defender: Player, coordinate: str) -> str:
        body = await self.request(defender, "POST", f"/game/{defender.session_id}/opponent-shot", json={"coordinate": coordinate})
        result = body.get("result")
        if result not in RESULTS:
            raise TechnicalDefeat(defender.name, "invalid opponent-shot result")
        defender.received.add(coordinate)
        expected = shot_result(defender.ships, defender.received, coordinate)
        if result != expected:
            raise TechnicalDefeat(defender.name, f"dishonest shot result for {coordinate}: expected {expected}, got {result}")
        return result

    async def submit_result(self, player: Player, result: str) -> None:
        body = await self.request(player, "POST", f"/game/{player.session_id}/shot/result", json={"result": result})
        if body != {"status": "accepted"}:
            raise TechnicalDefeat(player.name, "shot result was not accepted")

    async def close_all(self) -> None:
        for player in self.players:
            if player.session_id:
                try:
                    await self.client.post(f"{player.base_url}/game/{player.session_id}/close")
                except httpx.HTTPError:
                    pass
        await self.client.aclose()

    async def play(self) -> tuple[str, str]:
        try:
            for player in self.players:
                await self.start(player)
            current = random.randrange(2)
            while True:
                attacker, defender = self.players[current], self.players[1 - current]
                coordinate = await self.get_shot(attacker)
                result = await self.defend(defender, coordinate)
                await self.submit_result(attacker, result)
                if len(defender.received) == 20:
                    return attacker.name, "all enemy ship cells were hit"
                if result == "miss":
                    current = 1 - current
        except TechnicalDefeat as error:
            winner = self.players[1] if error.loser == self.players[0].name else self.players[0]
            return winner.name, f"technical defeat of {error.loser}: {error.reason}"
        finally:
            await self.close_all()


async def run(first_url: str, second_url: str) -> None:
    winner, reason = await Arena(first_url, second_url).play()
    print(f"Winner: {winner}. Reason: {reason}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Battleship arena")
    parser.add_argument("first_url")
    parser.add_argument("second_url")
    args = parser.parse_args()
    asyncio.run(run(args.first_url, args.second_url))

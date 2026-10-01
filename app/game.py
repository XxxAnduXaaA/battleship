from __future__ import annotations

import random
from collections.abc import Iterable
from uuid import UUID

BOARD_SIZE = 10
FLEET = (4, 3, 3, 2, 2, 2, 1, 1, 1, 1)
RESULTS = {"miss", "hit", "killed"}
ALL_COORDINATES = tuple(f"{column}{row}" for column in "ABCDEFGHIJ" for row in range(1, 11))


def parse_coordinate(value: str) -> tuple[int, int]:
    if not isinstance(value, str) or len(value) not in (2, 3):
        raise ValueError("Coordinate must be in A1-J10 format")
    column, row = value[0], value[1:]
    if column not in "ABCDEFGHIJ" or not row.isdigit() or not 1 <= int(row) <= BOARD_SIZE:
        raise ValueError("Coordinate must be in A1-J10 format")
    return ord(column) - ord("A"), int(row) - 1


def coordinate(column: int, row: int) -> str:
    return f"{chr(ord('A') + column)}{row + 1}"


def validate_ships(ships: list[dict]) -> None:
    if not isinstance(ships, list) or sorted(len(ship.get("coordinates", [])) for ship in ships) != sorted(FLEET):
        raise ValueError("Ships must match the standard fleet: 4, 3, 3, 2, 2, 2, 1, 1, 1, 1")

    occupied: set[tuple[int, int]] = set()
    for ship in ships:
        cells = [parse_coordinate(cell) for cell in ship["coordinates"]]
        if len(cells) != len(set(cells)):
            raise ValueError("A ship cannot contain duplicate cells")
        columns = {cell[0] for cell in cells}
        rows = {cell[1] for cell in cells}
        if len(cells) > 1 and len(columns) != 1 and len(rows) != 1:
            raise ValueError("Ships must be straight")
        ordered = sorted(rows if len(columns) == 1 else columns)
        if ordered != list(range(ordered[0], ordered[0] + len(ordered))):
            raise ValueError("Ship cells must be consecutive")
        for cell in cells:
            if cell in occupied:
                raise ValueError("Ships cannot overlap")
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if (cell[0] + dx, cell[1] + dy) in occupied:
                        raise ValueError("Ships cannot touch, including diagonally")
        occupied.update(cells)


def standard_ships() -> list[dict[str, list[str]]]:
    """Randomly place the standard fleet, restarting from scratch whenever a ship can't be fit."""
    while True:
        try:
            return _random_ships()
        except ValueError:
            continue



def _random_ships() -> list[dict[str, list[str]]]:
    occupied: set[tuple[int, int]] = set()
    ships = []
    for size in FLEET:
        cells = _place_ship(size, occupied)
        occupied.update(cells)
        ships.append({"coordinates": [coordinate(*cell) for cell in cells]})
    return ships


def _place_ship(size: int, occupied: set[tuple[int, int]], attempts: int = 200) -> list[tuple[int, int]]:
    for _ in range(attempts):
        if random.choice((True, False)):
            col, row = random.randint(0, BOARD_SIZE - size), random.randint(0, BOARD_SIZE - 1)
            cells = [(col + i, row) for i in range(size)]
        else:
            col, row = random.randint(0, BOARD_SIZE - 1), random.randint(0, BOARD_SIZE - size)
            cells = [(col, row + i) for i in range(size)]
        if _fits(cells, occupied):
            return cells
    raise ValueError("Could not place a ship without collisions")


def _fits(cells: list[tuple[int, int]], occupied: set[tuple[int, int]]) -> bool:
    return all((cell[0] + dx, cell[1] + dy) not in occupied for cell in cells for dx in (-1, 0, 1) for dy in (-1, 0, 1))


def next_shot(known: dict[str, str]) -> str:
    """Hunt adjacent to an un-killed hit, otherwise use a checkerboard hunt."""
    for cell, result in known.items():
        if result != "hit":
            continue
        col, row = parse_coordinate(cell)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            candidate = (col + dx, row + dy)
            if 0 <= candidate[0] < BOARD_SIZE and 0 <= candidate[1] < BOARD_SIZE:
                name = coordinate(*candidate)
                if name not in known:
                    return name
    for cell in ALL_COORDINATES:
        col, row = parse_coordinate(cell)
        if (col + row) % 2 == 0 and cell not in known:
            return cell
    return next(cell for cell in ALL_COORDINATES if cell not in known)


def shot_result(ships: Iterable[dict], received: set[str], target: str) -> str:
    if target not in {cell for ship in ships for cell in ship["coordinates"]}:
        return "miss"
    ship = next(ship for ship in ships if target in ship["coordinates"])
    return "killed" if all(cell in received for cell in ship["coordinates"]) else "hit"

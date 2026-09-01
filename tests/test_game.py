import pytest

from app.game import shot_result, standard_ships, validate_ships


def test_standard_fleet_is_legal():
    validate_ships(standard_ships())

def test_result_changes_to_killed_after_last_deck():
    ships = [{"coordinates": ["A1", "A2"]}]
    assert shot_result(ships, {"A1"}, "A1") == "hit"
    assert shot_result(ships, {"A1", "A2"}, "A2") == "killed"

def test_miss():
    assert shot_result([{"coordinates": ["A1"]}], {"B1"}, "B1") == "miss"

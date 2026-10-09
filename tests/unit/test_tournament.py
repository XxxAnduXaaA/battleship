import json

import pytest

from arena.main import MatchResult
from arena.tournament import (
    MatchRecord,
    Participant,
    aggregate_standings,
    format_html_report,
    format_text_report,
    load_participants,
    round_robin_pairs,
)


def make_participants(count: int) -> list[Participant]:
    return [Participant(f"p{i}", f"http://localhost:{8000 + i}") for i in range(count)]


def test_round_robin_pairs_empty_and_single():
    assert round_robin_pairs(make_participants(0)) == []
    assert round_robin_pairs(make_participants(1)) == []


def test_round_robin_pairs_two():
    a, b = make_participants(2)
    assert round_robin_pairs([a, b]) == [(a, b)]


def test_round_robin_pairs_four_are_unique_and_complete():
    participants = make_participants(4)
    pairs = round_robin_pairs(participants)

    assert len(pairs) == 6  # C(4, 2)

    seen = {frozenset((first.name, second.name)) for first, second in pairs}
    assert len(seen) == 6  # no duplicates

    for first, second in pairs:
        assert first.name != second.name  # no self-pairs


def test_aggregate_standings_counts_points_and_technical_outcomes():
    participants = make_participants(3)
    p0, p1, p2 = participants

    records = [
        MatchRecord(p0.name, p1.name, MatchResult(p0.name, p1.name, "all enemy ship cells were hit", technical=False)),
        MatchRecord(p0.name, p2.name, MatchResult(p0.name, p2.name, "technical defeat of p2: timeout", technical=True)),
        MatchRecord(p1.name, p2.name, MatchResult(p1.name, p2.name, "all enemy ship cells were hit", technical=False)),
    ]

    standings = aggregate_standings(participants, records)
    by_name = {standing.name: standing for standing in standings}

    assert by_name["p0"].points == 2
    assert by_name["p0"].wins == 2
    assert by_name["p0"].losses == 0
    assert by_name["p0"].technical_wins == 1

    assert by_name["p1"].points == 1
    assert by_name["p1"].wins == 1
    assert by_name["p1"].losses == 1

    assert by_name["p2"].points == 0
    assert by_name["p2"].losses == 2
    assert by_name["p2"].technical_losses == 1

    # sorted by points descending
    assert [standing.name for standing in standings] == ["p0", "p1", "p2"]


def test_aggregate_standings_ignores_crashed_match_for_points():
    participants = make_participants(2)
    records = [MatchRecord(participants[0].name, participants[1].name, result=None, error="boom")]

    standings = aggregate_standings(participants, records)

    assert all(standing.points == 0 and standing.wins == 0 and standing.losses == 0 for standing in standings)


def test_aggregate_standings_tie_keeps_stable_name_order():
    participants = make_participants(4)
    p0, p1, p2, p3 = participants

    records = [
        MatchRecord(p0.name, p1.name, MatchResult(p0.name, p1.name, "won", technical=False)),
        MatchRecord(p2.name, p3.name, MatchResult(p2.name, p3.name, "won", technical=False)),
    ]

    standings = aggregate_standings(participants, records)
    tied_leaders = [standing.name for standing in standings if standing.points == 1]

    assert tied_leaders == ["p0", "p2"]


def test_load_participants_valid_file(tmp_path):
    config = tmp_path / "tournament.json"
    config.write_text(json.dumps([{"name": "a", "url": "http://localhost:8001/"}, {"name": "b", "url": "http://localhost:8002"}]))

    participants = load_participants(config)

    assert participants == [Participant("a", "http://localhost:8001"), Participant("b", "http://localhost:8002")]


def test_load_participants_rejects_duplicate_names(tmp_path):
    config = tmp_path / "tournament.json"
    config.write_text(json.dumps([{"name": "a", "url": "http://localhost:8001"}, {"name": "a", "url": "http://localhost:8002"}]))

    with pytest.raises(ValueError):
        load_participants(config)


def test_load_participants_rejects_too_few_entries(tmp_path):
    config = tmp_path / "tournament.json"
    config.write_text(json.dumps([{"name": "a", "url": "http://localhost:8001"}]))

    with pytest.raises(ValueError):
        load_participants(config)


def test_load_participants_rejects_non_array(tmp_path):
    config = tmp_path / "tournament.json"
    config.write_text(json.dumps({"name": "a", "url": "http://localhost:8001"}))

    with pytest.raises(ValueError):
        load_participants(config)


def test_format_text_report_contains_participants_and_reasons():
    participants = make_participants(2)
    records = [
        MatchRecord(participants[0].name, participants[1].name, MatchResult("p0", "p1", "all enemy ship cells were hit", technical=False))
    ]
    standings = aggregate_standings(participants, records)

    text = format_text_report(standings, records)

    assert "p0" in text
    assert "p1" in text
    assert "all enemy ship cells were hit" in text


def test_format_text_report_flags_crashed_match():
    participants = make_participants(2)
    records = [MatchRecord(participants[0].name, participants[1].name, result=None, error="boom")]
    standings = aggregate_standings(participants, records)

    text = format_text_report(standings, records)

    assert "НЕ ЗАВЕРШЁН" in text
    assert "boom" in text


def test_format_html_report_escapes_malicious_name_and_reason():
    malicious = Participant("<script>alert(1)</script>", "http://localhost:9001")
    honest = Participant("honest", "http://localhost:9002")
    participants = [malicious, honest]
    records = [
        MatchRecord(
            malicious.name,
            honest.name,
            MatchResult(honest.name, malicious.name, "technical defeat of <script>alert(1)</script>: <b>lied</b>", technical=True),
        )
    ]
    standings = aggregate_standings(participants, records)

    report = format_html_report(standings, records)

    assert "<script>alert(1)</script>" not in report
    assert "&lt;script&gt;" in report
    assert 'class="technical"' in report

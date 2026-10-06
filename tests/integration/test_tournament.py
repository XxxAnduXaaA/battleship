import asyncio

from arena.tournament import Participant, aggregate_standings, run_tournament

PARTICIPANTS = [
    Participant("service-a", "http://service-a:8000"),
    Participant("service-b", "http://service-b:8000"),
    Participant("service-c", "http://service-c:8000"),
]


def test_real_tournament_runs_every_pair_once_and_is_honest():
    records = asyncio.run(run_tournament(PARTICIPANTS))

    assert len(records) == 3  # C(3, 2)

    pairs_seen = {frozenset((record.first, record.second)) for record in records}
    assert len(pairs_seen) == 3  # every pair exactly once, no duplicates

    for record in records:
        assert record.result is not None, f"match runner crashed: {record.error}"
        # Both sides are the real reference service, so nobody should be caught lying/timing out.
        assert record.result.technical is False

    standings = aggregate_standings(PARTICIPANTS, records)
    assert sum(standing.wins for standing in standings) == len(records)
    assert sum(standing.points for standing in standings) == len(records)
    assert sum(standing.losses for standing in standings) == len(records)

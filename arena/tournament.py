from __future__ import annotations

import argparse
import asyncio
import html
import itertools
import json
from dataclasses import dataclass
from pathlib import Path

from arena.main import Arena, MatchResult, Player


@dataclass(frozen=True)
class Participant:
    name: str
    url: str


@dataclass
class MatchRecord:
    first: str
    second: str
    result: MatchResult | None
    error: str | None = None


@dataclass
class Standing:
    name: str
    points: int = 0
    wins: int = 0
    losses: int = 0
    technical_wins: int = 0
    technical_losses: int = 0


def load_participants(path: Path) -> list[Participant]:
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("tournament config must be a JSON array")

    participants = [Participant(name=entry["name"], url=entry["url"].rstrip("/")) for entry in data]

    names = [participant.name for participant in participants]
    if len(names) != len(set(names)):
        raise ValueError("duplicate participant names in tournament config")
    if len(participants) < 2:
        raise ValueError("need at least two participants to run a tournament")

    return participants


def round_robin_pairs(participants: list[Participant]) -> list[tuple[Participant, Participant]]:
    """Every unique pair of participants exactly once."""
    return list(itertools.combinations(participants, 2))


async def run_match(first: Participant, second: Participant) -> MatchRecord:
    arena = Arena(Player(first.name, first.url), Player(second.name, second.url))
    try:
        result = await arena.play()
    except Exception as error:  # a single broken match must never take down the whole tournament
        return MatchRecord(first.name, second.name, result=None, error=repr(error))
    return MatchRecord(first.name, second.name, result)


async def run_tournament(participants: list[Participant]) -> list[MatchRecord]:
    pairs = round_robin_pairs(participants)
    records = await asyncio.gather(*(run_match(first, second) for first, second in pairs))
    return list(records)


def aggregate_standings(participants: list[Participant], records: list[MatchRecord]) -> list[Standing]:
    table = {participant.name: Standing(participant.name) for participant in participants}

    for record in records:
        if record.result is None:
            # The runner itself crashed for this match - nobody is known to be at fault,
            # so no points change hands; the report flags it separately instead.
            continue
        winner, loser = record.result.winner, record.result.loser
        table[winner].points += 1
        table[winner].wins += 1
        table[loser].losses += 1
        if record.result.technical:
            table[winner].technical_wins += 1
            table[loser].technical_losses += 1

    return sorted(table.values(), key=lambda standing: (-standing.points, standing.name))


def format_text_report(standings: list[Standing], records: list[MatchRecord]) -> str:
    lines = ["Rank Participant          Points W  L  TechW TechL"]
    rank = 0
    previous_points: int | None = None
    for index, standing in enumerate(standings, start=1):
        if standing.points != previous_points:
            rank = index
            previous_points = standing.points
        lines.append(
            f"{rank:<4} {standing.name:<20} {standing.points:<6} {standing.wins:<2} {standing.losses:<2} "
            f"{standing.technical_wins:<5} {standing.technical_losses:<5}"
        )

    lines.append("")
    lines.append("Matches:")
    for record in records:
        if record.result is None:
            lines.append(f"  {record.first} vs {record.second} -> НЕ ЗАВЕРШЁН: {record.error}")
            continue
        marker = " [technical]" if record.result.technical else ""
        lines.append(
            f"  {record.first} vs {record.second} -> winner={record.result.winner} "
            f'reason="{record.result.reason}"{marker}'
        )

    return "\n".join(lines)


_HTML_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Battleship Tournament Report</title>
<style>
  body {{ font-family: sans-serif; margin: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
  th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.8rem; text-align: left; }}
  th {{ background: #eee; }}
  tr.technical {{ background: #fde2e2; }}
  tr.crashed {{ background: #fff3cd; }}
</style>
</head>
<body>
<h1>Standings</h1>
<table>
<tr><th>Rank</th><th>Participant</th><th>Points</th><th>Wins</th><th>Losses</th><th>Technical wins</th><th>Technical losses</th></tr>
{standings_rows}
</table>
<h1>Matches</h1>
<table>
<tr><th>Participant A</th><th>Participant B</th><th>Winner</th><th>Technical?</th><th>Reason</th></tr>
{match_rows}
</table>
</body>
</html>
"""


def format_html_report(standings: list[Standing], records: list[MatchRecord]) -> str:
    rank = 0
    previous_points: int | None = None
    standings_rows = []
    for index, standing in enumerate(standings, start=1):
        if standing.points != previous_points:
            rank = index
            previous_points = standing.points
        standings_rows.append(
            f"<tr><td>{rank}</td><td>{html.escape(standing.name)}</td><td>{standing.points}</td>"
            f"<td>{standing.wins}</td><td>{standing.losses}</td>"
            f"<td>{standing.technical_wins}</td><td>{standing.technical_losses}</td></tr>"
        )

    match_rows = []
    for record in records:
        if record.result is None:
            match_rows.append(
                f'<tr class="crashed"><td>{html.escape(record.first)}</td><td>{html.escape(record.second)}</td>'
                f"<td>N/A</td><td>N/A</td><td>не завершён: {html.escape(record.error or 'unknown failure')}</td></tr>"
            )
            continue
        row_class = ' class="technical"' if record.result.technical else ""
        match_rows.append(
            f"<tr{row_class}><td>{html.escape(record.first)}</td><td>{html.escape(record.second)}</td>"
            f"<td>{html.escape(record.result.winner)}</td><td>{'yes' if record.result.technical else 'no'}</td>"
            f"<td>{html.escape(record.result.reason)}</td></tr>"
        )

    return _HTML_TEMPLATE.format(standings_rows="\n".join(standings_rows), match_rows="\n".join(match_rows))


def write_html_report(standings: list[Standing], records: list[MatchRecord], path: Path) -> None:
    path.write_text(format_html_report(standings, records))


def main() -> None:
    parser = argparse.ArgumentParser(description="Battleship tournament runner")
    parser.add_argument("config", type=Path, help="Path to a tournament.json file")
    parser.add_argument("--html-out", type=Path, default=Path("tournament_report.html"))
    args = parser.parse_args()

    participants = load_participants(args.config)
    records = asyncio.run(run_tournament(participants))
    standings = aggregate_standings(participants, records)

    print(format_text_report(standings, records))
    write_html_report(standings, records, args.html_out)
    print(f"\nHTML report written to {args.html_out}")


if __name__ == "__main__":
    main()

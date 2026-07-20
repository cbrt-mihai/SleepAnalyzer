from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from sleep_analyzer.models import ScoreWeights
from sleep_analyzer.parse import ParseError, parse_file, parse_line


def test_simple_night():
    n = parse_line("Mon 13 Jul 4:05 - 11:15 Mon 13 Jul - 7.25, 0", 2026)
    assert n.duration_hours == pytest.approx(7 + 10 / 60, abs=1e-6)
    assert n.wakeups == 0
    assert n.rating == 7.25
    assert not n.is_composite


def test_optional_fields_and_stress_float():
    n = parse_line(
        "Mon 13 Jul 4:05 - 11:15 Mon 13 Jul - 7.25, 0, 5, alarm, 2.5",
        2026,
    )
    assert n.latency_minutes == 5
    assert n.wake_type == "alarm"
    assert n.stress == 2.5


def test_composite_segments():
    n = parse_line(
        "Sat 18 Jul 6:00 - 10:00[25/alarm] + 10:20 - 12:00[15/natural] "
        "Sat 18 Jul - 5.25, 1, stress:3.5",
        2026,
    )
    assert n.is_composite
    assert n.segment_count == 2
    assert n.duration_hours == pytest.approx(5 + 40 / 60, abs=1e-6)
    assert n.interruption_minutes == pytest.approx(20, abs=1e-6)
    assert n.segments[0].latency_minutes == 25
    assert n.segments[0].end_reason == "alarm"
    assert n.segments[1].end_reason == "natural"
    assert n.wake_type == "natural"
    assert n.latency_minutes == 25
    assert n.forced_mid_ends == 1
    base = n.rating - 0.5 * n.wakeups
    scored = ScoreWeights().score(n)
    assert scored < base


def test_call_end_reason():
    n = parse_line(
        "Sat 18 Jul 6:00 - 10:00[10/call] + 10:20 - 12:00[5/natural] "
        "Sat 18 Jul - 6, 0",
        2026,
    )
    assert n.segments[0].end_reason == "call"


def test_explicit_year_on_line():
    n = parse_line(
        "Mon 13 Jul 2025 4:05 - 11:15 Mon 13 Jul 2025 - 7, 0",
        2026,
    )
    assert n.start.year == 2025


def test_year_inference_across_boundary(tmp_path: Path):
    log = tmp_path / "log.txt"
    log.write_text(
        textwrap.dedent(
            """\
            Mon 1 Dec 4:00 - 11:00 Mon 1 Dec - 7, 0
            Thu 2 Jan 4:00 - 11:00 Thu 2 Jan - 6.5, 0
            """
        ),
        encoding="utf-8",
    )
    nights, warnings = parse_file(log, year=2025)
    assert len(nights) == 2
    assert nights[0].start.year == 2025
    assert nights[1].start.year == 2026
    assert any("inferred year" in w for w in warnings)


def test_nap_attachment(tmp_path: Path):
    log = tmp_path / "log.txt"
    log.write_text(
        textwrap.dedent(
            """\
            Sat 18 Jul 6:00 - 12:00 Sat 18 Jul - 6, 0, natural, 2
            Nap Sat 18 Jul 15:00 - 15:30
            """
        ),
        encoding="utf-8",
    )
    nights, _ = parse_file(log, year=2026)
    assert len(nights) == 1
    assert nights[0].nap_minutes == pytest.approx(30)


def test_bad_line_raises():
    with pytest.raises(ParseError):
        parse_line("not a sleep line", 2026)

from __future__ import annotations

from datetime import datetime

import pytest

from sleep_analyzer.metrics import analyze, filter_nights, sleep_debt
from sleep_analyzer.models import ScoreWeights, SleepNight, SleepSegment


def _night(
    day: int,
    start_h: int,
    end_h: int,
    rating: float = 7.0,
    *,
    month: int = 7,
    year: int = 2026,
) -> SleepNight:
    start = datetime(year, month, day, start_h, 0)
    end = datetime(year, month, day, end_h, 0)
    return SleepNight(
        start=start,
        end=end,
        rating=rating,
        wakeups=0,
        source_line=1,
        raw="",
        segments=(SleepSegment(start=start, end=end),),
    )


def test_filter_weekday_weekend():
    # 2026-07-13 Mon, 18 Sat
    nights = [_night(13, 4, 11), _night(18, 6, 12)]
    assert len(filter_nights(nights, "weekday")) == 1
    assert len(filter_nights(nights, "weekend")) == 1
    assert len(filter_nights(nights, "all")) == 2


def test_sleep_debt_cumulative():
    nights = [
        _night(13, 4, 10, rating=7),  # 6h
        _night(14, 4, 12, rating=7),  # 8h
    ]
    debt = sleep_debt(nights, target_hours=7.0)
    assert debt["nights"][0]["delta_hours"] == pytest.approx(-1.0)
    assert debt["nights"][1]["delta_hours"] == pytest.approx(1.0)
    assert debt["cumulative_balance_hours"] == pytest.approx(0.0)


def test_analyze_includes_sleep_debt():
    nights = [_night(13, 4, 11), _night(14, 4, 11), _night(15, 4, 11)]
    result = analyze(nights, weights=ScoreWeights(), min_samples=1)
    assert "sleep_debt" in result
    assert result["params"]["day_filter"] == "all"

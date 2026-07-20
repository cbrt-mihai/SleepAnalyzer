from __future__ import annotations

from datetime import datetime, timedelta

from .models import CYCLE_MINUTES, ScoreWeights, SleepNight, minutes_to_hhmm
from .metrics import bedtime_bins, cycle_stats, duration_bins, wake_bins


def _parse_hhmm(text: str) -> int:
    text = text.strip()
    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid time {text!r}; use H:MM")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Invalid time {text!r}")
    return hour * 60 + minute


def cycle_aligned_wake_times(
    bedtime_minutes: int, cycle_counts: list[int] | None = None
) -> list[dict]:
    if cycle_counts is None:
        cycle_counts = [4, 5, 6]
    rows = []
    for cycles in cycle_counts:
        wake = bedtime_minutes + cycles * CYCLE_MINUTES
        rows.append(
            {
                "cycles": cycles,
                "duration_hours": round(cycles * CYCLE_MINUTES / 60.0, 2),
                "wake_time": minutes_to_hhmm(wake),
            }
        )
    return rows


def nearest_cycle_duration(hours: float) -> dict:
    minutes = hours * 60.0
    cycles = max(1, int(round(minutes / CYCLE_MINUTES)))
    aligned_min = cycles * CYCLE_MINUTES
    return {
        "cycles": cycles,
        "hours": round(aligned_min / 60.0, 2),
        "delta_minutes": round(aligned_min - minutes, 1),
    }


def build_recommendations(
    nights: list[SleepNight],
    analysis: dict,
    weights: ScoreWeights | None = None,
    bin_minutes: int = 30,
    min_samples: int = 2,
    bedtime: str | None = None,
) -> dict:
    weights = weights or ScoreWeights()
    # If strict min-samples yields nothing, fall back to single-night bins.
    bed_bins = analysis["bedtime_bins"] or [
        b.__dict__ for b in bedtime_bins(nights, weights, bin_minutes, 1)
    ]
    dur_bins = analysis["duration_bins"] or [
        b.__dict__ for b in duration_bins(nights, weights, bin_minutes, 1)
    ]
    wake_b = analysis["wake_bins"] or [
        b.__dict__ for b in wake_bins(nights, weights, bin_minutes, 1)
    ]
    cycles = analysis["cycle_stats"] or cycle_stats(nights, weights, 1)

    best_bed = bed_bins[0] if bed_bins else None
    best_dur = dur_bins[0] if dur_bins else None
    best_wake = wake_b[0] if wake_b else None
    best_cycle = cycles[0] if cycles else None

    target_duration = (
        best_dur["mean_duration"]
        if best_dur
        else sum(n.duration_hours for n in nights) / len(nights)
    )
    aligned = nearest_cycle_duration(target_duration)

    low_n = len(nights) < 14
    confidence = (
        "low" if len(nights) < 14 else ("moderate" if len(nights) < 30 else "reasonable")
    )

    tonight = None
    if bedtime:
        bed_min = _parse_hhmm(bedtime)
        preferred_cycles = [best_cycle["cycles"]] if best_cycle else [5]
        base = preferred_cycles[0]
        cycle_list = sorted({max(3, base - 1), base, base + 1, aligned["cycles"]})
        tonight = {
            "bedtime": minutes_to_hhmm(bed_min),
            "wake_options": cycle_aligned_wake_times(bed_min, cycle_list),
            "preferred_cycles": base,
        }
    elif best_bed is not None:
        start_s, end_s = best_bed["label"].split("–")
        bed_min = (_parse_hhmm(start_s) + _parse_hhmm(end_s)) // 2
        base = best_cycle["cycles"] if best_cycle else aligned["cycles"]
        cycle_list = sorted({max(3, base - 1), base, base + 1})
        tonight = {
            "bedtime": minutes_to_hhmm(bed_min),
            "wake_options": cycle_aligned_wake_times(bed_min, cycle_list),
            "preferred_cycles": base,
            "note": "Bedtime taken from midpoint of best historical bedtime window",
        }

    return {
        "confidence": confidence,
        "low_sample_size": low_n,
        "sample_n": len(nights),
        "best_bedtime_window": best_bed,
        "best_duration_window": best_dur,
        "best_wake_window": best_wake,
        "best_cycle": best_cycle,
        "target_duration_hours": round(target_duration, 2),
        "cycle_aligned_duration": aligned,
        "tonight": tonight,
        "caveats": _caveats(nights, analysis, low_n, min_samples),
    }


def _caveats(
    nights: list[SleepNight],
    analysis: dict,
    low_n: bool,
    min_samples: int,
) -> list[str]:
    notes: list[str] = []
    if low_n:
        notes.append(
            f"Only {len(nights)} nights logged — treat recommendations as tentative "
            "until you have ~2–4 weeks of data."
        )
    if not analysis["bedtime_bins"]:
        notes.append(
            f"No bedtime bin met min-samples={min_samples}; rankings fell back to looser grouping."
        )
    jet = analysis["consistency"].get("social_jet_lag_hours")
    if jet is not None and abs(jet) > 1.0:
        notes.append(
            f"Weekend sleep midpoint shifts by {jet:+.1f}h vs weekdays (social jet lag)."
        )
    if analysis["trend"]["label"] == "worsening":
        notes.append("Recent ratings trend lower than earlier nights in this log.")
    elif analysis["trend"]["label"] == "improving":
        notes.append("Recent ratings trend higher than earlier nights in this log.")
    debt = analysis.get("sleep_debt") or {}
    bal = debt.get("cumulative_balance_hours")
    if bal is not None and bal <= -3:
        notes.append(
            f"Sleep balance vs target is {bal:+.1f}h cumulative "
            "(negative means short of your best-duration target)."
        )
    return notes


def suggest_wake_from_bedtime(bedtime: str, cycles: int = 5) -> str:
    wake_min = _parse_hhmm(bedtime) + cycles * CYCLE_MINUTES
    return minutes_to_hhmm(wake_min)


def format_schedule_example(bedtime: str, cycles: int = 5) -> dict:
    bed_min = _parse_hhmm(bedtime)
    wake_min = bed_min + cycles * CYCLE_MINUTES
    now = datetime.now().replace(second=0, microsecond=0)
    bed_dt = now.replace(hour=bed_min // 60, minute=bed_min % 60)
    wake_dt = bed_dt + timedelta(minutes=cycles * CYCLE_MINUTES)
    return {
        "bedtime": minutes_to_hhmm(bed_min),
        "wake": minutes_to_hhmm(wake_min),
        "cycles": cycles,
        "example_bed": bed_dt.isoformat(timespec="minutes"),
        "example_wake": wake_dt.isoformat(timespec="minutes"),
    }

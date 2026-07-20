from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, median, pstdev
from typing import Callable

import numpy as np

from .models import CYCLE_MINUTES, ScoreWeights, SleepNight, minutes_to_hhmm


@dataclass
class BinStat:
    label: str
    start_value: float
    count: int
    mean_score: float
    mean_rating: float
    mean_wakeups: float
    mean_duration: float


@dataclass
class SummaryStats:
    n: int
    date_start: str
    date_end: str
    duration_mean: float
    duration_median: float
    duration_std: float
    rating_mean: float
    rating_median: float
    rating_std: float
    wakeups_mean: float
    wakeups_median: float
    wakeups_std: float
    score_mean: float
    score_median: float
    score_std: float


def _safe_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return float(pstdev(values))


def summarize(nights: list[SleepNight], weights: ScoreWeights) -> SummaryStats:
    durations = [n.duration_hours for n in nights]
    ratings = [n.rating for n in nights]
    wakeups = [float(n.wakeups) for n in nights]
    scores = [weights.score(n) for n in nights]
    return SummaryStats(
        n=len(nights),
        date_start=nights[0].start.date().isoformat(),
        date_end=nights[-1].end.date().isoformat(),
        duration_mean=mean(durations),
        duration_median=median(durations),
        duration_std=_safe_std(durations),
        rating_mean=mean(ratings),
        rating_median=median(ratings),
        rating_std=_safe_std(ratings),
        wakeups_mean=mean(wakeups),
        wakeups_median=median(wakeups),
        wakeups_std=_safe_std(wakeups),
        score_mean=mean(scores),
        score_median=median(scores),
        score_std=_safe_std(scores),
    )


def _bin_key(value: float, bin_size: float) -> float:
    return (value // bin_size) * bin_size


def bin_metric(
    nights: list[SleepNight],
    value_fn: Callable[[SleepNight], float],
    weights: ScoreWeights,
    bin_size: float,
    min_samples: int,
    label_fn: Callable[[float, float], str],
) -> list[BinStat]:
    buckets: dict[float, list[SleepNight]] = defaultdict(list)
    for night in nights:
        buckets[_bin_key(value_fn(night), bin_size)].append(night)

    stats: list[BinStat] = []
    for start in sorted(buckets):
        group = buckets[start]
        if len(group) < min_samples:
            continue
        end = start + bin_size
        stats.append(
            BinStat(
                label=label_fn(start, end),
                start_value=start,
                count=len(group),
                mean_score=mean(weights.score(n) for n in group),
                mean_rating=mean(n.rating for n in group),
                mean_wakeups=mean(n.wakeups for n in group),
                mean_duration=mean(n.duration_hours for n in group),
            )
        )
    stats.sort(key=lambda b: (-b.mean_score, -b.count, b.start_value))
    return stats


def time_label(start: float, end: float) -> str:
    return f"{minutes_to_hhmm(int(start))}–{minutes_to_hhmm(int(end))}"


def duration_label(start: float, end: float) -> str:
    return f"{start:.1f}–{end:.1f}h"


def bedtime_bins(
    nights: list[SleepNight], weights: ScoreWeights, bin_minutes: int, min_samples: int
) -> list[BinStat]:
    return bin_metric(
        nights,
        lambda n: float(n.bedtime_minutes),
        weights,
        float(bin_minutes),
        min_samples,
        time_label,
    )


def wake_bins(
    nights: list[SleepNight], weights: ScoreWeights, bin_minutes: int, min_samples: int
) -> list[BinStat]:
    return bin_metric(
        nights,
        lambda n: float(n.wake_minutes),
        weights,
        float(bin_minutes),
        min_samples,
        time_label,
    )


def midpoint_bins(
    nights: list[SleepNight], weights: ScoreWeights, bin_minutes: int, min_samples: int
) -> list[BinStat]:
    return bin_metric(
        nights,
        lambda n: float(n.midpoint_minutes),
        weights,
        float(bin_minutes),
        min_samples,
        time_label,
    )


def duration_bins(
    nights: list[SleepNight], weights: ScoreWeights, bin_minutes: int, min_samples: int
) -> list[BinStat]:
    bin_hours = bin_minutes / 60.0
    return bin_metric(
        nights,
        lambda n: n.duration_hours,
        weights,
        bin_hours,
        min_samples,
        duration_label,
    )


def bedtime_duration_grid(
    nights: list[SleepNight],
    weights: ScoreWeights,
    bin_minutes: int,
    min_samples: int,
) -> list[dict]:
    """Mean score for bedtime × duration cells with enough samples."""
    bin_hours = bin_minutes / 60.0
    cells: dict[tuple[float, float], list[SleepNight]] = defaultdict(list)
    for night in nights:
        key = (
            _bin_key(float(night.bedtime_minutes), float(bin_minutes)),
            _bin_key(night.duration_hours, bin_hours),
        )
        cells[key].append(night)

    rows: list[dict] = []
    for (bed_start, dur_start), group in sorted(cells.items()):
        if len(group) < min_samples:
            continue
        rows.append(
            {
                "bedtime": time_label(bed_start, bed_start + bin_minutes),
                "duration": duration_label(dur_start, dur_start + bin_hours),
                "count": len(group),
                "mean_score": mean(weights.score(n) for n in group),
                "mean_rating": mean(n.rating for n in group),
            }
        )
    rows.sort(key=lambda r: (-r["mean_score"], -r["count"]))
    return rows


def cycle_stats(nights: list[SleepNight], weights: ScoreWeights, min_samples: int) -> list[dict]:
    buckets: dict[int, list[SleepNight]] = defaultdict(list)
    for night in nights:
        # Nearest whole cycle count for grouping.
        buckets[int(round(night.cycle_count))].append(night)

    rows: list[dict] = []
    for cycles, group in sorted(buckets.items()):
        if len(group) < min_samples or cycles <= 0:
            continue
        rows.append(
            {
                "cycles": cycles,
                "hours": round(cycles * CYCLE_MINUTES / 60.0, 2),
                "count": len(group),
                "mean_score": mean(weights.score(n) for n in group),
                "mean_rating": mean(n.rating for n in group),
                "mean_duration": mean(n.duration_hours for n in group),
            }
        )
    rows.sort(key=lambda r: (-r["mean_score"], -r["count"]))
    return rows


def consistency(nights: list[SleepNight]) -> dict:
    bed = [float(n.bedtime_minutes) for n in nights]
    mid = [float(n.midpoint_minutes) for n in nights]
    weekday = [n for n in nights if not n.is_weekend]
    weekend = [n for n in nights if n.is_weekend]

    weekday_mid = mean(n.midpoint_minutes for n in weekday) if weekday else None
    weekend_mid = mean(n.midpoint_minutes for n in weekend) if weekend else None
    jet_lag_hours = None
    if weekday_mid is not None and weekend_mid is not None:
        # Circular-ish difference on 24h clock, preferring signed delay of weekend.
        diff = weekend_mid - weekday_mid
        if diff > 12 * 60:
            diff -= 24 * 60
        elif diff < -12 * 60:
            diff += 24 * 60
        jet_lag_hours = diff / 60.0

    return {
        "bedtime_std_minutes": _safe_std(bed),
        "midpoint_std_minutes": _safe_std(mid),
        "duration_std_hours": _safe_std([n.duration_hours for n in nights]),
        "weekday_n": len(weekday),
        "weekend_n": len(weekend),
        "weekday_midpoint": minutes_to_hhmm(int(round(weekday_mid))) if weekday_mid is not None else None,
        "weekend_midpoint": minutes_to_hhmm(int(round(weekend_mid))) if weekend_mid is not None else None,
        "weekday_duration_mean": mean(n.duration_hours for n in weekday) if weekday else None,
        "weekend_duration_mean": mean(n.duration_hours for n in weekend) if weekend else None,
        "weekday_rating_mean": mean(n.rating for n in weekday) if weekday else None,
        "weekend_rating_mean": mean(n.rating for n in weekend) if weekend else None,
        "social_jet_lag_hours": jet_lag_hours,
        "social_jet_lag_flag": bool(jet_lag_hours is not None and abs(jet_lag_hours) > 1.0),
    }


def _corr_pairs(series: dict[str, list[float]]) -> list[dict]:
    keys = list(series.keys())
    rows: list[dict] = []
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            xa = np.asarray(series[a], dtype=float)
            xb = np.asarray(series[b], dtype=float)
            if len(xa) < 3 or np.std(xa) == 0 or np.std(xb) == 0:
                corr = float("nan")
            else:
                corr = float(np.corrcoef(xa, xb)[0, 1])
            rows.append({"a": a, "b": b, "r": corr})
    rows.sort(key=lambda r: (0 if np.isnan(r["r"]) else -abs(r["r"])))
    return rows


def correlations(nights: list[SleepNight], weights: ScoreWeights) -> list[dict]:
    # Human-readable labels for the report / JSON (not internal field keys).
    series: dict[str, list[float]] = {
        "duration": [n.duration_hours for n in nights],
        "bedtime": [float(n.bedtime_minutes) for n in nights],
        "wake time": [float(n.wake_minutes) for n in nights],
        "sleep midpoint": [float(n.midpoint_minutes) for n in nights],
        "wakeups": [float(n.wakeups) for n in nights],
        "rating": [n.rating for n in nights],
        "score": [weights.score(n) for n in nights],
        "interruption min": [n.interruption_minutes for n in nights],
        "time in bed": [n.time_in_bed_hours for n in nights],
    }
    stress_nights = [n for n in nights if n.stress is not None]
    latency_nights = [n for n in nights if n.latency_minutes is not None]

    rows = _corr_pairs(series)
    if len(stress_nights) >= 3:
        stress_series = {
            "stress": [float(n.stress) for n in stress_nights],  # type: ignore[arg-type]
            "rating": [n.rating for n in stress_nights],
            "score": [weights.score(n) for n in stress_nights],
            "duration": [n.duration_hours for n in stress_nights],
            "wakeups": [float(n.wakeups) for n in stress_nights],
        }
        for row in _corr_pairs(stress_series):
            if "stress" in (row["a"], row["b"]):
                rows.append(row)
        rows.sort(key=lambda r: (0 if np.isnan(r["r"]) else -abs(r["r"])))

    if len(latency_nights) >= 3:
        lat_series = {
            "latency min": [float(n.latency_minutes) for n in latency_nights],  # type: ignore[arg-type]
            "rating": [n.rating for n in latency_nights],
            "score": [weights.score(n) for n in latency_nights],
            "duration": [n.duration_hours for n in latency_nights],
        }
        for row in _corr_pairs(lat_series):
            if "latency min" in (row["a"], row["b"]):
                rows.append(row)
        rows.sort(key=lambda r: (0 if np.isnan(r["r"]) else -abs(r["r"])))

    return rows


def _group_means(
    nights: list[SleepNight],
    key_fn,
    weights: ScoreWeights,
    min_samples: int,
) -> list[dict]:
    buckets: dict[str, list[SleepNight]] = defaultdict(list)
    for night in nights:
        key = key_fn(night)
        if key is None:
            continue
        buckets[str(key)].append(night)

    rows: list[dict] = []
    for label, group in sorted(buckets.items(), key=lambda kv: kv[0]):
        if len(group) < min_samples:
            continue
        rows.append(
            {
                "label": label,
                "count": len(group),
                "mean_score": mean(weights.score(n) for n in group),
                "mean_rating": mean(n.rating for n in group),
                "mean_duration": mean(n.duration_hours for n in group),
                "mean_wakeups": mean(n.wakeups for n in group),
            }
        )
    rows.sort(key=lambda r: (-r["mean_score"], -r["count"]))
    return rows


def _latency_bucket(minutes: float | None) -> str | None:
    if minutes is None:
        return None
    if minutes <= 5:
        return "0–5 min"
    if minutes <= 15:
        return "6–15 min"
    if minutes <= 30:
        return "16–30 min"
    return "31+ min"


def factor_analysis(
    nights: list[SleepNight],
    weights: ScoreWeights,
    min_samples: int,
) -> dict:
    return {
        "coverage": {
            "latency": sum(1 for n in nights if n.latency_minutes is not None),
            "wake_type": sum(1 for n in nights if n.wake_type is not None),
            "stress": sum(1 for n in nights if n.stress is not None),
            "nap": sum(1 for n in nights if n.nap_minutes > 0),
            "fragmented": sum(1 for n in nights if n.segment_count > 1),
            "n": len(nights),
        },
        "by_latency": _group_means(
            nights,
            lambda n: _latency_bucket(n.latency_minutes),
            weights,
            min_samples,
        ),
        "by_wake_type": _group_means(
            nights,
            lambda n: n.wake_type,
            weights,
            min_samples,
        ),
        "by_mid_end_reason": _mid_end_reason_groups(nights, weights, min_samples),
        "by_stress": _group_means(
            nights,
            lambda n: f"stress {n.stress}" if n.stress is not None else None,
            weights,
            min_samples,
        ),
        "by_nap": _group_means(
            nights,
            lambda n: "nap" if n.nap_minutes > 0 else "no nap",
            weights,
            min_samples,
        ),
        "by_fragmented": _group_means(
            nights,
            lambda n: "composite" if n.is_composite else "continuous",
            weights,
            min_samples,
        ),
    }


def _mid_end_reason_groups(
    nights: list[SleepNight],
    weights: ScoreWeights,
    min_samples: int,
) -> list[dict]:
    """Group composite nights by how non-final segments ended."""
    buckets: dict[str, list[SleepNight]] = defaultdict(list)
    for night in nights:
        if not night.is_composite:
            continue
        reasons = {
            seg.end_reason
            for seg in night.segments[:-1]
            if seg.end_reason
        }
        if not reasons:
            buckets["mid:unspecified"].append(night)
            continue
        for reason in reasons:
            buckets[f"mid:{reason}"].append(night)

    rows: list[dict] = []
    for label, group in sorted(buckets.items()):
        # Deduplicate nights that had multiple mid reasons counted once each bucket.
        unique = list({id(n): n for n in group}.values())
        if len(unique) < min_samples:
            continue
        rows.append(
            {
                "label": label,
                "count": len(unique),
                "mean_score": mean(weights.score(n) for n in unique),
                "mean_rating": mean(n.rating for n in unique),
                "mean_duration": mean(n.duration_hours for n in unique),
                "mean_wakeups": mean(n.wakeups for n in unique),
            }
        )
    rows.sort(key=lambda r: (-r["mean_score"], -r["count"]))
    return rows


def rolling_means(nights: list[SleepNight], window: int = 7) -> list[dict]:
    rows: list[dict] = []
    for i in range(len(nights)):
        start = max(0, i + 1 - window)
        chunk = nights[start : i + 1]
        rows.append(
            {
                "date": nights[i].end.date().isoformat(),
                "rating": nights[i].rating,
                "duration": nights[i].duration_hours,
                "rolling_rating": mean(n.rating for n in chunk),
                "rolling_duration": mean(n.duration_hours for n in chunk),
                "window": len(chunk),
            }
        )
    return rows


def trend_direction(nights: list[SleepNight], window: int = 7) -> dict:
    if len(nights) < 4:
        return {"label": "insufficient_data", "rating_delta": None, "duration_delta": None}

    half = max(2, len(nights) // 2)
    early = nights[:half]
    late = nights[-half:]
    rating_delta = mean(n.rating for n in late) - mean(n.rating for n in early)
    duration_delta = mean(n.duration_hours for n in late) - mean(n.duration_hours for n in early)

    if rating_delta > 0.25:
        label = "improving"
    elif rating_delta < -0.25:
        label = "worsening"
    else:
        label = "stable"

    return {
        "label": label,
        "rating_delta": rating_delta,
        "duration_delta": duration_delta,
        "early_n": len(early),
        "late_n": len(late),
        "window_hint": window,
    }


def best_and_worst(nights: list[SleepNight], weights: ScoreWeights, k: int = 3) -> dict:
    ranked = sorted(nights, key=lambda n: weights.score(n), reverse=True)
    return {
        "best": [n.to_dict(weights) for n in ranked[:k]],
        "worst": [n.to_dict(weights) for n in ranked[-k:][::-1]],
    }


def filter_nights(nights: list[SleepNight], day_filter: str = "all") -> list[SleepNight]:
    key = (day_filter or "all").lower()
    if key in {"all", "any", ""}:
        return list(nights)
    if key in {"weekday", "weekdays"}:
        return [n for n in nights if not n.is_weekend]
    if key in {"weekend", "weekends"}:
        return [n for n in nights if n.is_weekend]
    raise ValueError("day_filter must be all, weekday, or weekend")


def sleep_debt(nights: list[SleepNight], target_hours: float) -> dict:
    """Per-night and cumulative balance vs a target duration (hours)."""
    rows: list[dict] = []
    cumulative = 0.0
    for night in nights:
        delta = night.duration_hours - target_hours
        cumulative += delta
        rows.append(
            {
                "date": night.end.date().isoformat(),
                "duration_hours": round(night.duration_hours, 3),
                "target_hours": round(target_hours, 3),
                "delta_hours": round(delta, 3),
                "cumulative_balance_hours": round(cumulative, 3),
            }
        )
    last7 = rows[-7:] if rows else []
    return {
        "target_hours": round(target_hours, 3),
        "nights": rows,
        "cumulative_balance_hours": round(cumulative, 3) if rows else 0.0,
        "last_7_balance_hours": round(
            sum(r["delta_hours"] for r in last7), 3
        )
        if last7
        else 0.0,
        "nights_below_target": sum(1 for r in rows if r["delta_hours"] < 0),
        "nights_at_or_above_target": sum(1 for r in rows if r["delta_hours"] >= 0),
    }


def analyze(
    nights: list[SleepNight],
    weights: ScoreWeights | None = None,
    bin_minutes: int = 30,
    min_samples: int = 2,
    day_filter: str = "all",
) -> dict:
    weights = weights or ScoreWeights()
    filtered = filter_nights(nights, day_filter)
    if not filtered:
        raise ValueError(f"No nights left after day_filter={day_filter!r}")

    duration_bin_rows = [
        b.__dict__ for b in duration_bins(filtered, weights, bin_minutes, min_samples)
    ]
    target_hours = (
        duration_bin_rows[0]["mean_duration"]
        if duration_bin_rows
        else mean(n.duration_hours for n in filtered)
    )

    return {
        "summary": summarize(filtered, weights).__dict__,
        "bedtime_bins": [
            b.__dict__ for b in bedtime_bins(filtered, weights, bin_minutes, min_samples)
        ],
        "wake_bins": [
            b.__dict__ for b in wake_bins(filtered, weights, bin_minutes, min_samples)
        ],
        "midpoint_bins": [
            b.__dict__
            for b in midpoint_bins(filtered, weights, bin_minutes, min_samples)
        ],
        "duration_bins": duration_bin_rows,
        "bedtime_duration_grid": bedtime_duration_grid(
            filtered, weights, bin_minutes, min_samples
        ),
        "cycle_stats": cycle_stats(filtered, weights, min_samples),
        "consistency": consistency(filtered),
        "correlations": correlations(filtered, weights),
        "factors": factor_analysis(filtered, weights, min_samples),
        "rolling": rolling_means(filtered),
        "trend": trend_direction(filtered),
        "extremes": best_and_worst(filtered, weights),
        "sleep_debt": sleep_debt(filtered, target_hours),
        "nights": [n.to_dict(weights) for n in filtered],
        "params": {
            "wake_weight": weights.wake,
            "fragment_weight": weights.fragment,
            "gap_weight": weights.gap,
            "forced_mid_weight": weights.forced_mid,
            "bin_minutes": bin_minutes,
            "min_samples": min_samples,
            "day_filter": day_filter,
            "n_total": len(nights),
            "n_filtered": len(filtered),
        },
    }

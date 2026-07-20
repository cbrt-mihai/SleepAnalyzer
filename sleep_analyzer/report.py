from __future__ import annotations

from .models import SleepSegment, format_segments, minutes_to_hhmm, parse_iso_minutes


def _hr() -> str:
    return "-" * 64


def _fmt_num(value: float | None, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}{suffix}"


def _print_bin_table(title: str, bins: list[dict], top: int = 5) -> list[str]:
    lines = [title]
    if not bins:
        lines.append("  (no bins met min-samples)")
        return lines
    lines.append(
        f"  {'Window':<16} {'n':>3} {'score':>7} {'rating':>7} {'wakeups':>8} {'dur':>6}"
    )
    for row in bins[:top]:
        lines.append(
            f"  {row['label']:<16} {row['count']:>3} "
            f"{row['mean_score']:>7.2f} {row['mean_rating']:>7.2f} "
            f"{row['mean_wakeups']:>8.2f} {row['mean_duration']:>5.2f}h"
        )
    return lines


def render_report(
    analysis: dict,
    recommendations: dict,
    warnings: list[str] | None = None,
) -> str:
    s = analysis["summary"]
    c = analysis["consistency"]
    t = analysis["trend"]
    lines: list[str] = []

    lines.append("SLEEP ANALYZER REPORT")
    lines.append(_hr())
    params = analysis["params"]
    filter_note = ""
    if params.get("day_filter") and params["day_filter"] != "all":
        filter_note = (
            f"  |  filter={params['day_filter']} "
            f"({params.get('n_filtered', s['n'])}/{params.get('n_total', s['n'])})"
        )
    lines.append(
        f"Nights: {s['n']}  |  Range: {s['date_start']} → {s['date_end']}"
        f"{filter_note}"
    )
    lines.append(
        f"Duration: mean {_fmt_num(s['duration_mean'], 2, 'h')}  "
        f"median {_fmt_num(s['duration_median'], 2, 'h')}  "
        f"std {_fmt_num(s['duration_std'], 2, 'h')}"
    )
    lines.append(
        f"Rating:   mean {_fmt_num(s['rating_mean'])}  "
        f"median {_fmt_num(s['rating_median'])}  "
        f"std {_fmt_num(s['rating_std'])}"
    )
    lines.append(
        f"Wakeups:  mean {_fmt_num(s['wakeups_mean'])}  "
        f"median {_fmt_num(s['wakeups_median'])}  "
        f"std {_fmt_num(s['wakeups_std'])}"
    )
    lines.append(
        f"Score:    mean {_fmt_num(s['score_mean'])}  "
        f"(rating − {params['wake_weight']} × wakeups; "
        f"composite: −{params.get('fragment_weight', 0.25)}×extra segments, "
        f"−{params.get('gap_weight', 0.5)}×gap hours, "
        f"−{params.get('forced_mid_weight', 0.15)}×forced mid-ends)"
    )
    factors = analysis.get("factors") or {}
    cov = factors.get("coverage") or {}
    if cov:
        lines.append(
            "Optional fields logged: "
            f"latency {cov.get('latency', 0)}/{cov.get('n', 0)}, "
            f"wake type {cov.get('wake_type', 0)}/{cov.get('n', 0)}, "
            f"stress {cov.get('stress', 0)}/{cov.get('n', 0)}, "
            f"naps {cov.get('nap', 0)}, "
            f"interrupted nights {cov.get('fragmented', 0)}"
        )

    if warnings:
        lines.append("")
        lines.append("Parse warnings")
        lines.append(_hr())
        for w in warnings:
            lines.append(f"  • {w}")

    lines.append("")
    lines.append("RECOMMENDATIONS")
    lines.append(_hr())
    lines.append(
        f"Confidence: {recommendations['confidence']} "
        f"(n={recommendations['sample_n']})"
    )
    if recommendations.get("best_bedtime_window"):
        b = recommendations["best_bedtime_window"]
        lines.append(
            f"Best bedtime window:  {b['label']}  "
            f"(score {b['mean_score']:.2f}, n={b['count']})"
        )
    if recommendations.get("best_duration_window"):
        d = recommendations["best_duration_window"]
        lines.append(
            f"Best duration window: {d['label']}  "
            f"(score {d['mean_score']:.2f}, n={d['count']})"
        )
    if recommendations.get("best_wake_window"):
        w = recommendations["best_wake_window"]
        lines.append(
            f"Best wake window:     {w['label']}  "
            f"(score {w['mean_score']:.2f}, n={w['count']})"
        )
    aligned = recommendations["cycle_aligned_duration"]
    lines.append(
        f"Target duration:      {recommendations['target_duration_hours']:.2f}h  "
        f"[mean asleep time in best duration bin]"
    )
    lines.append(
        f"  ↳ cycle-aligned:    ≈ {aligned['hours']:.2f}h / {aligned['cycles']} cycles  "
        f"[nearest multiple of 90 min to that target — scheduling aid, not a separate bin]"
    )
    if recommendations.get("best_cycle"):
        cy = recommendations["best_cycle"]
        lines.append(
            f"Best cycle bucket:    {cy['cycles']} cycles "
            f"(ideal length {cy['hours']:.2f}h = {cy['cycles']}×90m; "
            f"score {cy['mean_score']:.2f}, n={cy['count']})  "
            f"[nights grouped by round(duration/90m); may differ from cycle-aligned above]"
        )
        if cy.get("mean_duration") is not None:
            lines.append(
                f"  ↳ actual mean dur in bucket: {cy['mean_duration']:.2f}h"
            )

    tonight = recommendations.get("tonight")
    if tonight:
        lines.append("")
        lines.append(
            f"If you go to bed at {tonight['bedtime']}:"
            + (f"  [{tonight['note']}]" if tonight.get("note") else "")
        )
        for opt in tonight["wake_options"]:
            marker = " ← preferred" if opt["cycles"] == tonight["preferred_cycles"] else ""
            lines.append(
                f"  → wake {opt['wake_time']}  "
                f"({opt['cycles']} cycles / {opt['duration_hours']:.2f}h){marker}"
            )

    for caveat in recommendations.get("caveats", []):
        lines.append(f"  ! {caveat}")

    debt = analysis.get("sleep_debt")
    if debt:
        lines.append("")
        lines.append("Sleep debt / balance")
        lines.append(_hr())
        lines.append(
            f"Target: {debt['target_hours']:.2f}h  "
            f"(same as best duration-bin mean)"
        )
        lines.append(
            f"Cumulative balance: {debt['cumulative_balance_hours']:+.2f}h  "
            f"(negative = short of target)"
        )
        lines.append(
            f"Last 7 nights balance: {debt['last_7_balance_hours']:+.2f}h  |  "
            f"below target: {debt['nights_below_target']}  |  "
            f"at/above: {debt['nights_at_or_above_target']}"
        )
        recent = debt["nights"][-5:]
        if recent:
            lines.append("  Recent (date  dur  Δ  cumulative):")
            for row in recent:
                lines.append(
                    f"    {row['date']}  {row['duration_hours']:.2f}h  "
                    f"{row['delta_hours']:+.2f}h  "
                    f"cum {row['cumulative_balance_hours']:+.2f}h"
                )

    lines.append("")
    lines.extend(
        _print_bin_table("Bedtime bins (by score)", analysis["bedtime_bins"])
    )
    lines.append("")
    lines.extend(
        _print_bin_table("Duration bins (by score)", analysis["duration_bins"])
    )
    lines.append("")
    lines.extend(_print_bin_table("Wake bins (by score)", analysis["wake_bins"]))
    lines.append("")
    lines.extend(
        _print_bin_table("Midpoint bins (by score)", analysis["midpoint_bins"])
    )

    grid = analysis["bedtime_duration_grid"]
    lines.append("")
    lines.append("Bedtime × duration grid")
    lines.append(_hr())
    if not grid:
        lines.append("  (no cells met min-samples)")
    else:
        lines.append(f"  {'Bedtime':<16} {'Duration':<12} {'n':>3} {'score':>7} {'rating':>7}")
        for row in grid[:8]:
            lines.append(
                f"  {row['bedtime']:<16} {row['duration']:<12} "
                f"{row['count']:>3} {row['mean_score']:>7.2f} {row['mean_rating']:>7.2f}"
            )

    lines.append("")
    lines.append("Consistency / social jet lag")
    lines.append(_hr())
    lines.append(
        f"Bedtime std: {_fmt_num(c['bedtime_std_minutes'], 1, ' min')}  |  "
        f"Midpoint std: {_fmt_num(c['midpoint_std_minutes'], 1, ' min')}  |  "
        f"Duration std: {_fmt_num(c['duration_std_hours'], 2, 'h')}"
    )
    lines.append(
        f"Weekday midpoint: {c['weekday_midpoint'] or 'n/a'} "
        f"(n={c['weekday_n']}, dur {_fmt_num(c['weekday_duration_mean'], 2, 'h')}, "
        f"rating {_fmt_num(c['weekday_rating_mean'])})"
    )
    lines.append(
        f"Weekend midpoint: {c['weekend_midpoint'] or 'n/a'} "
        f"(n={c['weekend_n']}, dur {_fmt_num(c['weekend_duration_mean'], 2, 'h')}, "
        f"rating {_fmt_num(c['weekend_rating_mean'])})"
    )
    if c["social_jet_lag_hours"] is not None:
        flag = "  [FLAG >1h]" if c["social_jet_lag_flag"] else ""
        lines.append(
            f"Social jet lag: {c['social_jet_lag_hours']:+.2f}h (weekend − weekday){flag}"
        )

    if factors:
        lines.append("")
        lines.append("Factors (optional fields)")
        lines.append(_hr())
        for title, key in (
            ("By latency (initial)", "by_latency"),
            ("By final wake / end reason", "by_wake_type"),
            ("By mid-segment end reason", "by_mid_end_reason"),
            ("By stress", "by_stress"),
            ("By nap", "by_nap"),
            ("By continuity", "by_fragmented"),
        ):
            rows = factors.get(key) or []
            lines.append(title)
            if not rows:
                lines.append("  (need more labeled nights for this factor)")
                continue
            lines.append(
                f"  {'Group':<14} {'n':>3} {'score':>7} {'rating':>7} {'dur':>6}"
            )
            for row in rows:
                lines.append(
                    f"  {row['label']:<14} {row['count']:>3} "
                    f"{row['mean_score']:>7.2f} {row['mean_rating']:>7.2f} "
                    f"{row['mean_duration']:>5.2f}h"
                )

    lines.append("")
    lines.append("Correlations (|r| ranked)")
    lines.append(_hr())
    lines.append(
        "  How strongly two measures rise/fall together (−1…+1). "
        "Not cause→effect."
    )
    corrs = [row for row in analysis["correlations"] if row["r"] == row["r"]]  # not NaN
    if not corrs:
        lines.append("  (need ≥3 nights with variance)")
    else:
        for row in corrs[:10]:
            lines.append(f"  {row['a']:>16} ↔ {row['b']:<16}  r={row['r']:+.2f}")

    lines.append("")
    lines.append("Trend")
    lines.append(_hr())
    if t["rating_delta"] is None:
        lines.append("  Insufficient data for early/late comparison")
    else:
        lines.append(
            f"  Direction: {t['label']}  |  "
            f"rating Δ {_fmt_num(t['rating_delta'], 2)}  |  "
            f"duration Δ {_fmt_num(t['duration_delta'], 2, 'h')}"
        )

    def _night_span(n: dict) -> str:
        segs = n.get("segments") or []
        if segs:
            built = [
                SleepSegment(
                    start=parse_iso_minutes(s["start"]),
                    end=parse_iso_minutes(s["end"]),
                    latency_minutes=s.get("latency_minutes"),
                    end_reason=s.get("end_reason"),
                )
                for s in segs
            ]
            return format_segments(built)
        start = parse_iso_minutes(n["start"])
        end = parse_iso_minutes(n["end"])
        return format_segments(
            [
                SleepSegment(
                    start=start,
                    end=end,
                    latency_minutes=n.get("latency_minutes"),
                    end_reason=n.get("wake_type"),
                )
            ]
        )

    def _extras(n: dict) -> str:
        bits: list[str] = []
        if n.get("is_composite"):
            bits.append("composite")
            if n.get("total_latency_minutes") is not None:
                bits.append(f"Σlat {n['total_latency_minutes']:.0f}m")
            if n.get("sleep_efficiency") is not None:
                bits.append(f"eff {n['sleep_efficiency'] * 100:.0f}%")
        elif n.get("latency_minutes") is not None:
            bits.append(f"lat {n['latency_minutes']:.0f}m")
        if n.get("wake_type") and not n.get("is_composite"):
            bits.append(str(n["wake_type"]))
        if n.get("stress") is not None:
            bits.append(f"stress {n['stress']}")
        if n.get("nap_minutes"):
            bits.append(f"nap {n['nap_minutes']:.0f}m")
        if n.get("segment_count", 1) > 1:
            bits.append(f"gap {n.get('interruption_minutes', 0):.0f}m")
        return f"  [{', '.join(bits)}]" if bits else ""

    extremes = analysis["extremes"]
    lines.append("")
    lines.append("Best nights")
    lines.append(_hr())
    for n in extremes["best"]:
        lines.append(
            f"  {_night_span(n)}  "
            f"dur {n['duration_hours']:.2f}h  rating {n['rating']}  "
            f"wakeups {n['wakeups']}  score {n['score']}{_extras(n)}"
        )
    lines.append("Worst nights")
    for n in extremes["worst"]:
        lines.append(
            f"  {_night_span(n)}  "
            f"dur {n['duration_hours']:.2f}h  rating {n['rating']}  "
            f"wakeups {n['wakeups']}  score {n['score']}{_extras(n)}"
        )

    lines.append("")
    lines.append("All nights")
    lines.append(_hr())
    lines.append(
        f"  {'Sleep':<42} {'Dur':>5} {'Rate':>5} {'W':>2} {'Score':>6}  Mid  Notes"
    )
    for n in analysis["nights"]:
        span = _night_span(n)
        lines.append(
            f"  {span:<42} "
            f"{n['duration_hours']:>4.2f}h {n['rating']:>5} {n['wakeups']:>2} "
            f"{n['score']:>6.2f}  {minutes_to_hhmm(n['midpoint_minutes'])}"
            f"{_extras(n)}"
        )

    lines.append("")
    return "\n".join(lines)

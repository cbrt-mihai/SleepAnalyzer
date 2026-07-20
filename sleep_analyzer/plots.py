from __future__ import annotations

from pathlib import Path

from .models import minutes_to_hhmm


def generate_plots(analysis: dict, output_dir: str | Path) -> list[Path]:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise SystemExit(
            "matplotlib is required for --plot. Install with: pip install matplotlib"
        ) from exc

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    nights = analysis["nights"]
    written: list[Path] = []

    # Bedtime vs rating
    fig, ax = plt.subplots(figsize=(7, 4.5))
    x = [n["bedtime_minutes"] for n in nights]
    y = [n["rating"] for n in nights]
    ax.scatter(x, y, c=[n["score"] for n in nights], cmap="viridis", s=60, edgecolors="k")
    ax.set_xlabel("Bedtime")
    ax.set_ylabel("Rating")
    ax.set_title("Bedtime vs rating")
    ticks = sorted(set(x))
    ax.set_xticks(ticks)
    ax.set_xticklabels([minutes_to_hhmm(t) for t in ticks], rotation=45, ha="right")
    fig.tight_layout()
    path = output_dir / "bedtime_vs_rating.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    written.append(path)

    # Duration vs rating
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.scatter(
        [n["duration_hours"] for n in nights],
        [n["rating"] for n in nights],
        c=[n["wakeups"] for n in nights],
        cmap="coolwarm",
        s=60,
        edgecolors="k",
    )
    ax.set_xlabel("Duration (hours)")
    ax.set_ylabel("Rating")
    ax.set_title("Duration vs rating (color = wakeups)")
    fig.tight_layout()
    path = output_dir / "duration_vs_rating.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    written.append(path)

    # Bin bar charts
    for key, title, filename in (
        ("bedtime_bins", "Mean score by bedtime bin", "bedtime_bins.png"),
        ("duration_bins", "Mean score by duration bin", "duration_bins.png"),
        ("wake_bins", "Mean score by wake bin", "wake_bins.png"),
    ):
        bins = analysis[key]
        if not bins:
            continue
        fig, ax = plt.subplots(figsize=(7, 4.5))
        labels = [b["label"] for b in bins]
        scores = [b["mean_score"] for b in bins]
        ax.bar(range(len(bins)), scores, color="#3d7ea6")
        ax.set_xticks(range(len(bins)))
        ax.set_xticklabels(labels, rotation=45, ha="right")
        ax.set_ylabel("Mean score")
        ax.set_title(title)
        fig.tight_layout()
        path = output_dir / filename
        fig.savefig(path, dpi=140)
        plt.close(fig)
        written.append(path)

    # Weekday vs weekend
    weekday = [n for n in nights if not n["is_weekend"]]
    weekend = [n for n in nights if n["is_weekend"]]
    fig, axes = plt.subplots(1, 2, figsize=(8, 4))
    for ax, values, label in (
        (axes[0], [n["rating"] for n in weekday], "Weekday rating"),
        (axes[1], [n["rating"] for n in weekend], "Weekend rating"),
    ):
        if values:
            ax.hist(values, bins=min(5, len(values)), color="#5b8c5a", edgecolor="white")
        ax.set_title(f"{label} (n={len(values)})")
        ax.set_xlabel("Rating")
    fig.suptitle("Weekday vs weekend ratings")
    fig.tight_layout()
    path = output_dir / "weekday_weekend.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    written.append(path)

    # Rolling trend
    rolling = analysis["rolling"]
    if rolling:
        fig, ax1 = plt.subplots(figsize=(8, 4.5))
        dates = [r["date"] for r in rolling]
        ax1.plot(dates, [r["rating"] for r in rolling], "o-", color="#3d7ea6", label="Rating")
        ax1.plot(
            dates,
            [r["rolling_rating"] for r in rolling],
            "-",
            color="#1b3a4b",
            label="Rolling rating",
        )
        ax1.set_ylabel("Rating")
        ax1.set_xlabel("Wake date")
        ax2 = ax1.twinx()
        ax2.plot(
            dates,
            [r["rolling_duration"] for r in rolling],
            "--",
            color="#c45c26",
            label="Rolling duration",
        )
        ax2.set_ylabel("Duration (h)")
        ax1.set_title("Rating & duration trend")
        ax1.tick_params(axis="x", rotation=45)
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="best")
        fig.tight_layout()
        path = output_dir / "rolling_trend.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        written.append(path)

    return written

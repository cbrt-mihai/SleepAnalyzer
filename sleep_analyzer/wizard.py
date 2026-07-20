"""Interactive setup wizard for SleepAnalyzer."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from sleep_analyzer.cli import run_analysis
from sleep_analyzer.config import (
    AnalyzeConfig,
    default_config,
    find_config_file,
    load_config,
    save_config,
)

SAMPLE_LINES = """\
# SleepAnalyzer sample log — edit or replace with your nights
# Format: Weekday Day Month H:MM - H:MM Weekday Day Month - Rating, Wakeups
# Optional after wakeups: latency minutes, wake type, stress 1-5, nap:MIN
# Interrupted sleep: join segments with +
#
Mon 13 Jul 4:05 - 11:15 Mon 13 Jul - 7.25, 0, 5, natural, 2
Tue 14 Jul 3:40 - 9:45 Tue 14 Jul - 6, 0, 20, alarm, 3
Wed 15 Jul 5:25 - 10:58 Wed 15 Jul - 7, 0, 0, natural, 1
"""


def _prompt(question: str, default: str | None = None) -> str:
    if default is None:
        suffix = ""
    else:
        suffix = f" [{default}]"
    while True:
        try:
            raw = input(f"{question}{suffix}: ").strip()
        except EOFError:
            print()
            raise SystemExit(1) from None
        except KeyboardInterrupt:
            print("\nCancelled.")
            raise SystemExit(130) from None
        if raw:
            return raw
        if default is not None:
            return default
        print("  Please enter a value.")


def _prompt_yes_no(question: str, default: bool = False) -> bool:
    default_s = "Y/n" if default else "y/N"
    while True:
        raw = _prompt(f"{question} ({default_s})", default="y" if default else "n")
        key = raw.lower()
        if key in {"y", "yes"}:
            return True
        if key in {"n", "no"}:
            return False
        print("  Please answer y or n.")


def _prompt_int(question: str, default: int, minimum: int | None = None) -> int:
    while True:
        raw = _prompt(question, str(default))
        try:
            value = int(raw)
        except ValueError:
            print("  Enter a whole number.")
            continue
        if minimum is not None and value < minimum:
            print(f"  Must be >= {minimum}.")
            continue
        return value


def _prompt_float(question: str, default: float, minimum: float | None = None) -> float:
    while True:
        raw = _prompt(question, str(default))
        try:
            value = float(raw)
        except ValueError:
            print("  Enter a number.")
            continue
        if minimum is not None and value < minimum:
            print(f"  Must be >= {minimum}.")
            continue
        return value


def _prompt_optional(question: str) -> str | None:
    raw = _prompt(f"{question} (Enter to skip)", "")
    return raw or None


def _print_format_help() -> None:
    print(
        """
Log format (one night per line)
-------------------------------
  Weekday Day Month H:MM - H:MM Weekday Day Month - Rating, Wakeups

Optional after wakeups (typical order):
  latency:  rough minutes to fall asleep (e.g. 0, 10, 25 or latency:15)
  end:      alarm | natural | call | other
  stress:   1-5
  nap:      nap:40   (or a separate line: Nap Sat 18 Jul 15:30 - 16:00)

Composite / interrupted sleep — tag each segment [latency/end_reason]:
  Sat 18 Jul 6:00 - 10:00[25/call] + 10:20 - 12:00[15/natural] Sat 18 Jul - 5.25, 1, stress:4

Example:
  Mon 13 Jul 4:05 - 11:15 Mon 13 Jul - 7.25, 0, 5, natural, 2
"""
    )


def run_wizard() -> int:
    print("=" * 64)
    print("SleepAnalyzer wizard")
    print("=" * 64)
    print(
        "This walks you through analyzing a sleep log and choosing options.\n"
        "Press Ctrl+C at any time to cancel.\n"
    )

    base = default_config()
    existing = find_config_file()
    if existing is not None:
        print(f"Found config: {existing}")
        if _prompt_yes_no("Load it as starting defaults?", default=True):
            try:
                base = load_config(existing)
            except Exception as exc:  # noqa: BLE001
                print(f"  Could not load config ({exc}); using built-in defaults.")

    if _prompt_yes_no("Show the log format help first?", default=True):
        _print_format_help()

    default_log = str(base.log_file)
    log_raw = _prompt("Path to your sleep log file", default_log)
    log_path = Path(log_raw).expanduser()

    if not log_path.is_file():
        print(f"\nFile not found: {log_path}")
        if _prompt_yes_no("Create it with a short sample log you can edit?", default=True):
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(SAMPLE_LINES, encoding="utf-8")
            print(f"Created {log_path}")
            print("Edit that file with your nights, then re-run the wizard — or continue on the sample.")
            if not _prompt_yes_no("Analyze the sample file now?", default=True):
                print("OK. Add your data, then run: sleep-analyzer wizard")
                return 0
        else:
            print("Nothing to analyze. Exiting.")
            return 1

    year_default = base.year if base.year is not None else datetime.now().year
    year = _prompt_int(
        "Year for dates in the log (lines have no year)",
        year_default,
        minimum=1970,
    )

    print(
        "\nAnalysis tuning (defaults are fine for a first run).\n"
        "  min-samples  — bins need at least this many nights to rank\n"
        "  bin-minutes  — window size for bedtime/duration groups\n"
        "  wake-weight  — score = rating − weight × wakeups\n"
    )
    use_advanced = _prompt_yes_no("Change advanced analysis options?", default=False)
    if use_advanced:
        min_samples = _prompt_int("Minimum samples per bin", base.min_samples, minimum=1)
        bin_minutes = _prompt_int("Bin width in minutes", base.bin_minutes, minimum=1)
        wake_weight = _prompt_float(
            "Wakeup penalty weight", base.wake_weight, minimum=0.0
        )
    else:
        min_samples = base.min_samples
        bin_minutes = base.bin_minutes
        wake_weight = base.wake_weight

    bedtime_default = base.bedtime or ""
    bedtime = _prompt(
        "Candidate bedtime H:MM for cycle wake suggestions (Enter to skip)",
        bedtime_default,
    )
    bedtime = bedtime.strip() or None
    if bedtime:
        parts = bedtime.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            print("  Ignoring bedtime — expected H:MM.")
            bedtime = None

    plot = _prompt_yes_no("Generate PNG charts?", default=base.plot)
    output_dir = base.output_dir
    if plot:
        output_dir = Path(
            _prompt("Directory for charts", str(base.output_dir))
        ).expanduser()

    export_default = base.export_json is not None
    export = _prompt_yes_no("Also export a JSON report?", default=export_default)
    export_json: Path | None = None
    if export:
        export_json = Path(
            _prompt(
                "JSON output path",
                str(base.export_json or Path("output") / "report.json"),
            )
        ).expanduser()

    config = AnalyzeConfig(
        log_file=log_path,
        year=year,
        min_samples=min_samples,
        bin_minutes=bin_minutes,
        wake_weight=wake_weight,
        fragment_weight=base.fragment_weight,
        gap_weight=base.gap_weight,
        forced_mid_weight=base.forced_mid_weight,
        day_filter=base.day_filter,
        bedtime=bedtime,
        plot=plot,
        output_dir=output_dir,
        export_json=export_json,
    )

    print("\nReady to run with:")
    print(f"  log file     = {config.log_file}")
    print(f"  year         = {config.year}")
    print(f"  min-samples  = {config.min_samples}")
    print(f"  bin-minutes  = {config.bin_minutes}")
    print(f"  wake-weight  = {config.wake_weight}")
    print(f"  bedtime      = {config.bedtime or '(auto from best window)'}")
    print(f"  plots        = {config.plot} → {config.output_dir}")
    print(f"  export-json  = {config.export_json or '(none)'}")

    print("\nEquivalent command:")
    print("  sleep-analyzer   # if saved to sleep_analyzer.toml")
    print(
        f"  sleep-analyzer {config.log_file} --year {config.year} "
        f"--min-samples {config.min_samples} --bin-minutes {config.bin_minutes} "
        f"--wake-weight {config.wake_weight}"
        + (f" --bedtime {config.bedtime}" if config.bedtime else "")
        + (f" --plot --output-dir {config.output_dir}" if config.plot else "")
        + (f" --export-json {config.export_json}" if config.export_json else "")
    )

    if _prompt_yes_no("\nSave these settings to a config file?", default=True):
        cfg_path = Path(
            _prompt("Config path", str(existing or "sleep_analyzer.toml"))
        ).expanduser()
        saved = save_config(config, cfg_path)
        print(f"Wrote {saved}")
        print("Next time you can run: sleep-analyzer")

    if not _prompt_yes_no("\nRun analysis now?", default=True):
        print("Cancelled before analysis.")
        return 0

    print()
    return run_analysis(config)


if __name__ == "__main__":
    raise SystemExit(run_wizard())

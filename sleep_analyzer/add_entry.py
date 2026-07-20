"""Interactively append a sleep night (or nap) to a log file."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from sleep_analyzer.parse import ParseError, parse_line


def _prompt(question: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
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
    hint = "Y/n" if default else "y/N"
    while True:
        raw = _prompt(f"{question} ({hint})", "y" if default else "n").lower()
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("  Please answer y or n.")


def _default_date() -> str:
    now = datetime.now()
    return f"{now.strftime('%a')} {now.day} {now.strftime('%b')}"


def build_night_line_interactive() -> str:
    print(
        "Add a sleep night. Times are 24h. Leave optional fields blank to skip.\n"
        "Composite nights: add more than one segment.\n"
    )
    start_date = _prompt("Bed date (e.g. Mon 13 Jul or Mon 13 Jul 2026)", _default_date())
    segments: list[str] = []
    while True:
        n = len(segments) + 1
        default_span = "4:00 - 11:00" if not segments else ""
        span = _prompt(f"Segment {n} times (H:MM - H:MM)", default_span)
        if not span:
            if segments:
                break
            print("  Need at least one segment.")
            continue
        lat = _prompt(f"Segment {n} latency minutes (rough)", "")
        reason = _prompt(
            f"Segment {n} end reason (alarm/natural/call/other)",
            "",
        )
        tag = ""
        bits = [b for b in (lat, reason) if b]
        if bits:
            tag = f"[{'/'.join(bits)}]"
        segments.append(f"{span.strip()}{tag}")
        if not _prompt_yes_no("Add another segment (interruption)?", default=False):
            break

    end_date = _prompt("Wake date", start_date)
    rating = _prompt("Rating", "7")
    wakeups = _prompt("Times woken up", "0")

    extras: list[str] = []
    if len(segments) == 1 and "[" not in segments[0]:
        lat = _prompt("Latency minutes (rough)", "")
        if lat:
            extras.append(lat)
        reason = _prompt("End reason (alarm/natural/call/other)", "")
        if reason:
            extras.append(reason)
    stress = _prompt("Stress 1-5", "")
    if stress:
        extras.append(stress)

    meta = f"{rating}, {wakeups}"
    if extras:
        meta += ", " + ", ".join(extras)
    return f"{start_date} {' + '.join(segments)} {end_date} - {meta}"


def build_nap_line_interactive() -> str:
    date = _prompt("Nap date (e.g. Sat 18 Jul)", _default_date())
    span = _prompt("Nap times (H:MM - H:MM)", "15:00 - 15:40")
    return f"Nap {date} {span}"


def append_line(log_path: Path, line: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    existing = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"{prefix}{line.rstrip()}\n")


def run_add_cli(
    log_path: Path,
    year: int | None = None,
    line: str | None = None,
    nap: bool = False,
) -> int:
    try:
        if line:
            text = line.strip()
        elif nap:
            text = build_nap_line_interactive()
        else:
            if _prompt_yes_no("Log a daytime nap instead of a night?", default=False):
                text = build_nap_line_interactive()
            else:
                text = build_night_line_interactive()

        print(f"\nLine to append:\n  {text}")
        if line is None and not _prompt_yes_no("Write this to the log?", default=True):
            print("Cancelled.")
            return 0

        use_year = year if year is not None else datetime.now().year
        if not text.lower().startswith("nap "):
            parse_line(text, year=use_year)
        append_line(log_path, text)
    except ParseError as exc:
        print(f"Error: invalid entry: {exc}", file=sys.stderr)
        return 1
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 1

    print(f"Appended to {log_path}")
    return 0

from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta
from pathlib import Path

from .models import (
    END_REASON_ALIASES,
    LEGACY_LATENCY_MINUTES,
    SleepNight,
    SleepSegment,
)

# Night line:
# Mon 13 Jul 4:05 - 11:15 Mon 13 Jul - 7.25, 0, 5, natural, 2
# Sat 18 Jul 6:00 - 10:00[25/alarm] + 10:20 - 12:00[10/natural] Sat 18 Jul - 5.25, 1, stress:3.5
NIGHT_RE = re.compile(
    r"""
    ^\s*
    (?P<start_wd>\w+)\s+
    (?P<start_day>\d{1,2})\s+
    (?P<start_month>\w+)
    (?:\s+(?P<start_year>\d{4}))?\s+
    (?P<segments>.+?)\s+
    (?P<end_wd>\w+)\s+
    (?P<end_day>\d{1,2})\s+
    (?P<end_month>\w+)
    (?:\s+(?P<end_year>\d{4}))?\s*
    -\s*
    (?P<meta>.+?)
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)

SEGMENT_RE = re.compile(
    r"""
    (?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})
    (?:\s*\[(?P<seg_meta>[^\]]*)\])?
    """,
    re.VERBOSE,
)

# Nap Sat 18 Jul 15:30 - 16:10
# Nap Sat 18 Jul 2026 15:30 - 16:10
NAP_RE = re.compile(
    r"""
    ^\s*Nap\s+
    (?P<wd>\w+)\s+
    (?P<day>\d{1,2})\s+
    (?P<month>\w+)
    (?:\s+(?P<year>\d{4}))?\s+
    (?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE,
)

MONTH_LOOKUP = {
    **{name.lower(): i for i, name in enumerate(calendar.month_name) if name},
    **{name.lower(): i for i, name in enumerate(calendar.month_abbr) if name},
}


class ParseError(ValueError):
    pass


def _parse_month(token: str) -> int:
    key = token.strip().lower()
    if key not in MONTH_LOOKUP:
        raise ParseError(f"Unknown month: {token!r}")
    return MONTH_LOOKUP[key]


def _parse_time(token: str) -> tuple[int, int]:
    hour_s, minute_s = token.split(":")
    hour, minute = int(hour_s), int(minute_s)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ParseError(f"Invalid time: {token!r}")
    return hour, minute


def _build_datetime(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute)


def _normalize_end_reason(token: str) -> str | None:
    key = token.strip().lower().replace(" ", "-").replace("_", "-")
    return END_REASON_ALIASES.get(key)


# Backward-compatible name.
_normalize_wake_type = _normalize_end_reason


def _legacy_latency_minutes(token: str) -> float | None:
    key = re.sub(r"[\s_]+", "-", token.strip().lower())
    for candidate in (key, token.strip().lower(), key.replace("-", "_"), key.replace("-", "")):
        if candidate in LEGACY_LATENCY_MINUTES:
            return float(LEGACY_LATENCY_MINUTES[candidate])
    return None


def _parse_latency_minutes(value: str) -> float:
    legacy = _legacy_latency_minutes(value)
    if legacy is not None:
        return legacy
    try:
        minutes = float(value)
    except ValueError as exc:
        raise ParseError(
            f"Invalid latency {value!r}; use rough minutes (e.g. 0, 10, 25) "
            "or latency:15"
        ) from exc
    if minutes < 0 or minutes > 240:
        raise ParseError(f"Latency minutes out of range (0–240): {minutes}")
    return minutes


def _parse_meta(
    meta: str,
) -> tuple[float, int, float | None, str | None, float | None, float]:
    """Return rating, wakeups, latency_minutes, wake_type, stress, nap_minutes."""
    parts = [p.strip() for p in meta.split(",") if p.strip()]
    if len(parts) < 2:
        raise ParseError("Expected at least Rating, Wakeups after the final date")

    try:
        rating = float(parts[0])
        wakeups = int(parts[1])
    except ValueError as exc:
        raise ParseError("Rating must be a number and wakeups an integer") from exc

    latency_minutes: float | None = None
    wake_type: str | None = None
    stress: float | None = None
    nap_minutes = 0.0

    i = 2
    while i < len(parts):
        token = parts[i]
        lower = token.lower()

        if lower.startswith("latency:") or lower.startswith("lat:"):
            latency_minutes = _parse_latency_minutes(token.split(":", 1)[1])
            i += 1
            continue
        if (
            lower.startswith("wake:")
            or lower.startswith("wake-type:")
            or lower.startswith("waketype:")
            or lower.startswith("end:")
        ):
            value = token.split(":", 1)[1]
            wt = _normalize_end_reason(value)
            if wt is None:
                raise ParseError(
                    f"Unknown end reason: {value!r} "
                    "(use alarm, natural, call, or other)"
                )
            wake_type = wt
            i += 1
            continue
        if lower.startswith("stress:"):
            try:
                stress = float(token.split(":", 1)[1])
            except ValueError as exc:
                raise ParseError(f"Invalid stress value: {token!r}") from exc
            if not 1 <= stress <= 5:
                raise ParseError("Stress must be 1–5")
            i += 1
            continue
        if lower.startswith("nap:"):
            try:
                nap_minutes = float(token.split(":", 1)[1])
            except ValueError as exc:
                raise ParseError(f"Invalid nap minutes: {token!r}") from exc
            if nap_minutes < 0:
                raise ParseError("Nap minutes cannot be negative")
            i += 1
            continue

        legacy = _legacy_latency_minutes(token)
        if legacy is not None:
            latency_minutes = legacy
            i += 1
            continue

        wt = _normalize_end_reason(token)
        if wt is not None:
            wake_type = wt
            i += 1
            continue

        try:
            number = float(token)
        except ValueError as exc:
            raise ParseError(
                f"Unrecognized optional field {token!r}. "
                "Use latency minutes (e.g. 15 or latency:15), "
                "end reason (alarm/natural/call/other), stress:1-5, or nap:MIN"
            ) from exc

        # Bare numbers:
        #   before end reason → latency minutes
        #   after end reason (or after latency), 1–5 → stress
        #   otherwise nap minutes (prefer nap:MIN)
        if wake_type is not None and stress is None and 1 <= number <= 5:
            stress = number
        elif latency_minutes is None and 0 <= number <= 240:
            latency_minutes = number
        elif stress is None and 1 <= number <= 5:
            stress = number
        else:
            if number < 0:
                raise ParseError("Nap minutes cannot be negative")
            nap_minutes = number
        i += 1

    return rating, wakeups, latency_minutes, wake_type, stress, nap_minutes


def _parse_segment_meta(raw: str | None) -> tuple[float | None, str | None]:
    """Parse [10/alarm] or [10, call] or [lat:10 end:natural]."""
    if raw is None or not raw.strip():
        return None, None

    latency: float | None = None
    end_reason: str | None = None
    text = raw.strip()

    # Support slash form: 10/alarm
    if "/" in text and ":" not in text.split("/")[0]:
        left, right = text.split("/", 1)
        if left.strip():
            latency = _parse_latency_minutes(left.strip())
        if right.strip():
            end_reason = _normalize_end_reason(right.strip())
            if end_reason is None:
                raise ParseError(
                    f"Unknown segment end reason {right!r} "
                    "(use alarm, natural, call, or other)"
                )
        return latency, end_reason

    parts = re.split(r"[,;\s]+", text)
    for part in parts:
        if not part:
            continue
        lower = part.lower()
        if lower.startswith("lat:") or lower.startswith("latency:"):
            latency = _parse_latency_minutes(part.split(":", 1)[1])
            continue
        if lower.startswith("end:") or lower.startswith("wake:"):
            end_reason = _normalize_end_reason(part.split(":", 1)[1])
            if end_reason is None:
                raise ParseError(f"Unknown segment end reason in {part!r}")
            continue
        reason = _normalize_end_reason(part)
        if reason is not None:
            end_reason = reason
            continue
        try:
            latency = _parse_latency_minutes(part)
        except ParseError as exc:
            raise ParseError(
                f"Invalid segment tag [{raw}]; use [10/alarm] or [10, call]"
            ) from exc
    return latency, end_reason


def _parse_segments_text(
    segments_text: str,
) -> list[tuple[str, str, float | None, str | None]]:
    text = segments_text.strip()
    chunks = re.split(r"\s*\+\s*", text)
    pairs: list[tuple[str, str, float | None, str | None]] = []
    for chunk in chunks:
        match = SEGMENT_RE.fullmatch(chunk.strip())
        if not match:
            raise ParseError(
                f"Invalid time segment {chunk!r}; use H:MM - H:MM[lat/reason] "
                "(join interruptions with +)"
            )
        lat, reason = _parse_segment_meta(match.group("seg_meta"))
        pairs.append((match.group("start"), match.group("end"), lat, reason))
    if not pairs:
        raise ParseError("No time segments found")
    return pairs


def _build_segments(
    year: int,
    start_month: int,
    start_day: int,
    end_month: int,
    end_day: int,
    pairs: list[tuple[str, str, float | None, str | None]],
) -> list[SleepSegment]:
    base = datetime(year, start_month, start_day)
    segments: list[SleepSegment] = []
    prev_end: datetime | None = None

    for start_tok, end_tok, lat, reason in pairs:
        sh, sm = _parse_time(start_tok)
        eh, em = _parse_time(end_tok)
        start = base.replace(hour=sh, minute=sm)
        end = base.replace(hour=eh, minute=em)
        if end <= start:
            end += timedelta(days=1)

        if prev_end is not None:
            while start < prev_end:
                start += timedelta(days=1)
                end += timedelta(days=1)
            if end <= start:
                end += timedelta(days=1)

        if end <= start:
            raise ParseError("Wake time must be after segment start")

        segments.append(
            SleepSegment(
                start=start,
                end=end,
                latency_minutes=lat,
                end_reason=reason,
            )
        )
        prev_end = end

    total_h = sum(seg.duration_hours for seg in segments)
    if total_h > 20:
        raise ParseError(f"Implausible asleep duration ({total_h:.1f}h)")
    span_h = (segments[-1].end - segments[0].start).total_seconds() / 3600.0
    if span_h > 24:
        raise ParseError(f"Implausible time-in-bed span ({span_h:.1f}h)")

    return segments


def parse_night_line(
    line: str,
    year: int,
    line_no: int = 0,
) -> tuple[SleepNight, bool]:
    """Parse a night line. Returns (night, year_was_explicit_on_line)."""
    text = line.strip()
    match = NIGHT_RE.match(text)
    if not match:
        raise ParseError(
            "Expected: Weekday Day Month [Year] H:MM - H:MM[+ ...] "
            "Weekday Day Month [Year] - Rating, Wakeups[, ...]"
        )

    start_month = _parse_month(match.group("start_month"))
    end_month = _parse_month(match.group("end_month"))
    start_day = int(match.group("start_day"))
    end_day = int(match.group("end_day"))
    explicit_year = match.group("start_year") is not None
    start_year = int(match.group("start_year")) if match.group("start_year") else year
    # End year is informational for spans; segment builder uses start_year as base.
    pairs = _parse_segments_text(match.group("segments"))
    rating, wakeups, latency_minutes, wake_type, stress, nap_minutes = _parse_meta(
        match.group("meta")
    )

    segments = _build_segments(
        start_year, start_month, start_day, end_month, end_day, pairs
    )

    # Fill segment gaps from night-level fields when tags omitted.
    filled: list[SleepSegment] = []
    for idx, seg in enumerate(segments):
        lat = seg.latency_minutes
        reason = seg.end_reason
        if lat is None and idx == 0 and latency_minutes is not None:
            lat = latency_minutes
        if reason is None and idx == len(segments) - 1 and wake_type is not None:
            reason = wake_type
        # Single-segment night: night-level wake applies to the only segment.
        if reason is None and len(segments) == 1 and wake_type is not None:
            reason = wake_type
        if lat != seg.latency_minutes or reason != seg.end_reason:
            seg = SleepSegment(
                start=seg.start,
                end=seg.end,
                latency_minutes=lat,
                end_reason=reason,
            )
        filled.append(seg)
    segments = filled

    # Night-level summaries derived from segments when tagged.
    initial_latency = segments[0].latency_minutes
    if initial_latency is None:
        initial_latency = latency_minutes
    final_reason = segments[-1].end_reason
    if final_reason is None:
        final_reason = wake_type

    night = SleepNight(
        start=segments[0].start,
        end=segments[-1].end,
        rating=rating,
        wakeups=wakeups,
        source_line=line_no,
        raw=text,
        segments=tuple(segments),
        latency_minutes=initial_latency,
        wake_type=final_reason,
        stress=stress,
        nap_minutes=nap_minutes,
    )
    return night, explicit_year


def parse_nap_line(
    line: str, year: int, line_no: int = 0
) -> tuple[datetime, datetime, bool]:
    match = NAP_RE.match(line.strip())
    if not match:
        raise ParseError("Expected: Nap Weekday Day Month [Year] H:MM - H:MM")
    month = _parse_month(match.group("month"))
    day = int(match.group("day"))
    explicit = match.group("year") is not None
    use_year = int(match.group("year")) if explicit else year
    sh, sm = _parse_time(match.group("start"))
    eh, em = _parse_time(match.group("end"))
    start = _build_datetime(use_year, month, day, sh, sm)
    end = _build_datetime(use_year, month, day, eh, em)
    if end <= start:
        end += timedelta(days=1)
    minutes = (end - start).total_seconds() / 60.0
    if minutes <= 0 or minutes > 6 * 60:
        raise ParseError(f"Implausible nap length ({minutes:.0f} min)")
    return start, end, explicit


def parse_line(line: str, year: int, line_no: int = 0) -> SleepNight:
    """Backward-compatible helper: night lines only."""
    night, _ = parse_night_line(line, year, line_no)
    return night


def _attach_naps(
    nights: list[SleepNight],
    naps: list[tuple[datetime, datetime, int]],
    warnings: list[str],
) -> list[SleepNight]:
    if not naps:
        return nights

    # Sum nap minutes by wake-date preference, else start-date.
    by_wake: dict = {}
    by_start: dict = {}
    for start, end, line_no in naps:
        minutes = (end - start).total_seconds() / 60.0
        by_wake.setdefault(end.date(), 0.0)
        by_wake[end.date()] += minutes
        by_start.setdefault(start.date(), 0.0)
        by_start[start.date()] += minutes

    used_dates: set = set()
    updated: list[SleepNight] = []
    for night in nights:
        add = 0.0
        wake_d = night.end.date()
        start_d = night.start.date()
        if wake_d in by_wake:
            add += by_wake[wake_d]
            used_dates.add(wake_d)
        elif start_d in by_start:
            add += by_start[start_d]
            used_dates.add(start_d)
        if add:
            updated.append(night.with_nap_minutes(night.nap_minutes + add))
        else:
            updated.append(night)

    for start, end, line_no in naps:
        d = end.date()
        if d not in used_dates and start.date() not in used_dates:
            warnings.append(
                f"Line {line_no}: nap on {start.strftime('%Y-%m-%d')} "
                "could not be attached to a night"
            )
    return updated


def parse_file(
    path: str | Path,
    year: int | None = None,
) -> tuple[list[SleepNight], list[str]]:
    """Parse a sleep log file. Returns (nights, warnings)."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Sleep log not found: {path}")

    year_cursor = year if year is not None else datetime.now().year
    nights: list[SleepNight] = []
    naps: list[tuple[datetime, datetime, int]] = []
    warnings: list[str] = []
    previous: SleepNight | None = None

    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.lower().startswith("nap "):
            try:
                start, end, nap_explicit = parse_nap_line(
                    stripped, year=year_cursor, line_no=line_no
                )
            except ParseError as exc:
                warnings.append(f"Line {line_no}: {exc}")
                continue
            if nap_explicit:
                year_cursor = start.year
            elif previous is not None and start < previous.start:
                year_cursor += 1
                start, end, _ = parse_nap_line(
                    stripped, year=year_cursor, line_no=line_no
                )
            naps.append((start, end, line_no))
            continue

        try:
            night, explicit_year = parse_night_line(
                stripped, year=year_cursor, line_no=line_no
            )
        except ParseError as exc:
            warnings.append(f"Line {line_no}: {exc}")
            continue

        if explicit_year:
            year_cursor = night.start.year
        elif previous is not None and night.start < previous.start:
            # Crossed year boundary without an explicit year on the line.
            year_cursor += 1
            night, _ = parse_night_line(
                stripped, year=year_cursor, line_no=line_no
            )
            warnings.append(
                f"Line {line_no}: inferred year {year_cursor} "
                "(month/day went backwards from previous night)"
            )

        if previous is not None and night.start < previous.start:
            warnings.append(
                f"Line {line_no}: out-of-order date (before previous night); "
                "add an explicit year on the line or check --year"
            )
        if previous is not None and night.start < previous.end:
            warnings.append(
                f"Line {line_no}: overlaps previous night ending "
                f"{previous.end.strftime('%Y-%m-%d %H:%M')}"
            )

        nights.append(night)
        previous = night

    if not nights:
        raise ParseError(f"No valid sleep entries found in {path}")

    nights.sort(key=lambda n: n.start)
    nights = _attach_naps(nights, naps, warnings)
    return nights, warnings

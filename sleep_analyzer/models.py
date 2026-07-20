from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence


CYCLE_MINUTES = 90


@dataclass(frozen=True)
class ScoreWeights:
    """Weights for quality_score (continuous + composite penalties)."""

    wake: float = 0.5
    fragment: float = 0.25
    gap: float = 0.5
    forced_mid: float = 0.15

    def score(self, night: "SleepNight") -> float:
        return night.quality_score(
            self.wake,
            fragment_weight=self.fragment,
            gap_weight=self.gap,
            forced_mid_weight=self.forced_mid,
        )


# Rough minute equivalents if someone still uses old category words.
LEGACY_LATENCY_MINUTES = {
    "instant": 0,
    "immediate": 0,
    "fast": 10,
    "quick": 10,
    "slow": 25,
    "very-slow": 40,
    "very_slow": 40,
    "veryslow": 40,
    "very slow": 40,
}

# How a sleep segment ended.
END_REASON_ALIASES = {
    "alarm": "alarm",
    "natural": "natural",
    "no-alarm": "natural",
    "no_alarm": "natural",
    "spontaneous": "natural",
    "call": "call",
    "phone": "call",
    "phonecall": "call",
    "phone-call": "call",
    "other": "other",
    "noise": "other",
    "disturbance": "other",
    "interrupt": "other",
    "interrupted": "other",
}

# Planned or external mid-night ends (not a natural final wake).
FORCED_END_REASONS = frozenset({"alarm", "call", "other"})

# Backward-compatible alias used by older parse helpers.
WAKE_TYPE_ALIASES = END_REASON_ALIASES


@dataclass(frozen=True)
class SleepSegment:
    """One continuous asleep stretch within a night."""

    start: datetime
    end: datetime
    latency_minutes: float | None = None
    end_reason: str | None = None  # alarm | natural | call | other

    @property
    def duration_hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600.0

    def to_dict(self) -> dict:
        return {
            "start": self.start.isoformat(timespec="minutes"),
            "end": self.end.isoformat(timespec="minutes"),
            "latency_minutes": self.latency_minutes,
            "end_reason": self.end_reason,
            "duration_hours": round(self.duration_hours, 3),
        }


@dataclass(frozen=True)
class SleepNight:
    """One logged sleep bout with derived metrics."""

    start: datetime
    end: datetime
    rating: float
    wakeups: int
    source_line: int
    raw: str
    segments: tuple[SleepSegment, ...] = ()
    latency_minutes: float | None = None  # initial (first segment) latency
    wake_type: str | None = None  # final segment end reason
    stress: float | None = None
    nap_minutes: float = 0.0

    def __post_init__(self) -> None:
        if not self.segments:
            object.__setattr__(
                self,
                "segments",
                (
                    SleepSegment(
                        start=self.start,
                        end=self.end,
                        latency_minutes=self.latency_minutes,
                        end_reason=self.wake_type,
                    ),
                ),
            )

    @property
    def is_composite(self) -> bool:
        return self.segment_count > 1

    @property
    def duration_hours(self) -> float:
        """Asleep time only (sum of segments; excludes interruption gaps)."""
        return sum(seg.duration_hours for seg in self.segments)

    @property
    def duration_minutes(self) -> float:
        return self.duration_hours * 60.0

    @property
    def time_in_bed_hours(self) -> float:
        """First bedtime → final wake, including gaps."""
        return (self.end - self.start).total_seconds() / 3600.0

    @property
    def interruption_minutes(self) -> float:
        gap = (self.time_in_bed_hours - self.duration_hours) * 60.0
        return max(0.0, gap)

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    @property
    def total_latency_minutes(self) -> float | None:
        values = [s.latency_minutes for s in self.segments if s.latency_minutes is not None]
        if not values:
            return self.latency_minutes
        return float(sum(values))

    @property
    def sleep_efficiency(self) -> float | None:
        tib = self.time_in_bed_hours
        if tib <= 0:
            return None
        return self.duration_hours / tib

    @property
    def bedtime_minutes(self) -> int:
        """Minutes from midnight for bedtime (0–1439)."""
        return self.start.hour * 60 + self.start.minute

    @property
    def wake_minutes(self) -> int:
        return self.end.hour * 60 + self.end.minute

    @property
    def midpoint(self) -> datetime:
        # Midpoint of the overall bout (bed → final wake).
        return self.start + (self.end - self.start) / 2

    @property
    def midpoint_minutes(self) -> int:
        m = self.midpoint
        return m.hour * 60 + m.minute

    @property
    def is_weekend(self) -> bool:
        # Weekend classified by wake day (Sat/Sun).
        return self.end.weekday() >= 5

    @property
    def cycle_count(self) -> float:
        return self.duration_minutes / CYCLE_MINUTES

    @property
    def forced_mid_ends(self) -> int:
        """Non-final segments ended by alarm/call/other."""
        if not self.is_composite:
            return 0
        return sum(
            1
            for seg in self.segments[:-1]
            if seg.end_reason in FORCED_END_REASONS
        )

    def quality_score(
        self,
        wake_weight: float = 0.5,
        *,
        fragment_weight: float = 0.25,
        gap_weight: float = 0.5,
        forced_mid_weight: float = 0.15,
    ) -> float:
        """
        Continuous nights: rating − wake_weight × wakeups.

        Composite nights also subtract:
          fragment_weight × (segments − 1)
          gap_weight × interruption hours
          forced_mid_weight × mid-segments ended by alarm/call/other
        """
        score = self.rating - wake_weight * self.wakeups
        if self.is_composite:
            score -= fragment_weight * (self.segment_count - 1)
            score -= gap_weight * (self.interruption_minutes / 60.0)
            score -= forced_mid_weight * self.forced_mid_ends
        return score

    def with_nap_minutes(self, nap_minutes: float) -> SleepNight:
        return SleepNight(
            start=self.start,
            end=self.end,
            rating=self.rating,
            wakeups=self.wakeups,
            source_line=self.source_line,
            raw=self.raw,
            segments=self.segments,
            latency_minutes=self.latency_minutes,
            wake_type=self.wake_type,
            stress=self.stress,
            nap_minutes=nap_minutes,
        )

    def to_dict(self, weights: ScoreWeights | None = None) -> dict:
        w = weights or ScoreWeights()
        eff = self.sleep_efficiency
        return {
            "start": self.start.isoformat(timespec="minutes"),
            "end": self.end.isoformat(timespec="minutes"),
            "segments": [seg.to_dict() for seg in self.segments],
            "is_composite": self.is_composite,
            "rating": self.rating,
            "wakeups": self.wakeups,
            "latency_minutes": self.latency_minutes,
            "total_latency_minutes": self.total_latency_minutes,
            "wake_type": self.wake_type,
            "stress": self.stress,
            "nap_minutes": self.nap_minutes,
            "duration_hours": round(self.duration_hours, 3),
            "time_in_bed_hours": round(self.time_in_bed_hours, 3),
            "interruption_minutes": round(self.interruption_minutes, 1),
            "segment_count": self.segment_count,
            "forced_mid_ends": self.forced_mid_ends,
            "sleep_efficiency": None if eff is None else round(eff, 3),
            "bedtime_minutes": self.bedtime_minutes,
            "wake_minutes": self.wake_minutes,
            "midpoint_minutes": self.midpoint_minutes,
            "is_weekend": self.is_weekend,
            "cycle_count": round(self.cycle_count, 2),
            "score": round(w.score(self), 3),
            "source_line": self.source_line,
            "raw": self.raw,
        }


def minutes_to_hhmm(minutes: int) -> str:
    minutes = int(minutes) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def format_clock(dt: datetime) -> str:
    """Human clock like 'Mon 13 Jul 4:05' (no leading zero on hour)."""
    return f"{dt.strftime('%a')} {dt.day} {dt.strftime('%b')} {dt.hour}:{dt.minute:02d}"


def format_time(dt: datetime) -> str:
    return f"{dt.hour}:{dt.minute:02d}"


def format_span(start: datetime, end: datetime) -> str:
    """Readable bed→wake span; omits wake date when same calendar day."""
    if start.date() == end.date():
        return f"{format_clock(start)} → {format_time(end)}"
    return f"{format_clock(start)} → {format_clock(end)}"


def _format_segment_tag(seg: SleepSegment) -> str:
    bits: list[str] = []
    if seg.latency_minutes is not None:
        bits.append(f"{seg.latency_minutes:.0f}m")
    if seg.end_reason:
        bits.append(seg.end_reason)
    return f"[{'/'.join(bits)}]" if bits else ""


def format_segments(segments: Sequence[SleepSegment] | Sequence[tuple[datetime, datetime]]) -> str:
    if not segments:
        return ""

    normalized: list[SleepSegment] = []
    for item in segments:
        if isinstance(item, SleepSegment):
            normalized.append(item)
        else:
            start, end = item
            normalized.append(SleepSegment(start=start, end=end))

    first = normalized[0]
    parts = [f"{format_span(first.start, first.end)}{_format_segment_tag(first)}"]
    for seg in normalized[1:]:
        if seg.start.date() == first.start.date() and seg.end.date() == first.start.date():
            core = f"{format_time(seg.start)} → {format_time(seg.end)}"
        else:
            core = format_span(seg.start, seg.end)
        parts.append(f"{core}{_format_segment_tag(seg)}")
    return " + ".join(parts)


def parse_iso_minutes(value: str) -> datetime:
    return datetime.fromisoformat(value)

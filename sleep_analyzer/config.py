"""Load / save AnalyzeConfig from TOML or JSON files."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from sleep_analyzer.models import ScoreWeights

DEFAULT_CONFIG_NAMES = (
    "sleep_analyzer.toml",
    "sleep_analyzer.json",
    "config.toml",
    "config.json",
)

CONFIG_KEYS = (
    "log_file",
    "year",
    "min_samples",
    "bin_minutes",
    "wake_weight",
    "fragment_weight",
    "gap_weight",
    "forced_mid_weight",
    "day_filter",
    "bedtime",
    "plot",
    "output_dir",
    "export_json",
)


@dataclass
class AnalyzeConfig:
    log_file: Path
    year: int | None = None
    min_samples: int = 2
    bin_minutes: int = 30
    wake_weight: float = 0.5
    fragment_weight: float = 0.25
    gap_weight: float = 0.5
    forced_mid_weight: float = 0.15
    day_filter: str = "all"  # all | weekday | weekend
    bedtime: str | None = None
    plot: bool = False
    output_dir: Path = Path("output")
    export_json: Path | None = None

    def score_weights(self) -> ScoreWeights:
        return ScoreWeights(
            wake=self.wake_weight,
            fragment=self.fragment_weight,
            gap=self.gap_weight,
            forced_mid=self.forced_mid_weight,
        )


class ConfigError(ValueError):
    pass


def default_config() -> AnalyzeConfig:
    return AnalyzeConfig(log_file=Path("data/sleep_log.txt"))


def find_config_file(start: Path | None = None) -> Path | None:
    root = start or Path.cwd()
    for name in DEFAULT_CONFIG_NAMES:
        path = root / name
        if path.is_file():
            return path
    return None


def _load_toml(text: str) -> dict:
    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore
        except ModuleNotFoundError as exc:
            raise ConfigError(
                "Reading .toml configs requires Python 3.11+ (tomllib) "
                "or the 'tomli' package. Use sleep_analyzer.json instead, "
                "or: pip install tomli"
            ) from exc
    try:
        data = tomllib.loads(text)
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(f"Invalid TOML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("TOML config root must be a table")
    if "analyze" in data and isinstance(data["analyze"], dict):
        return dict(data["analyze"])
    return data


def _load_json(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("JSON config root must be an object")
    if "analyze" in data and isinstance(data["analyze"], dict):
        return dict(data["analyze"])
    return data


def _coerce(data: dict) -> AnalyzeConfig:
    unknown = sorted(k for k in data if k not in CONFIG_KEYS)
    if unknown:
        print(
            f"Warning: ignoring unknown config key(s): {', '.join(unknown)}",
            file=sys.stderr,
        )

    def get(key: str, default):
        return data[key] if key in data else default

    log_file = Path(str(get("log_file", "data/sleep_log.txt"))).expanduser()
    year = get("year", None)
    if year is not None:
        year = int(year)
    bedtime = get("bedtime", None)
    if bedtime is not None:
        bedtime = str(bedtime).strip() or None
    export_json = get("export_json", None)
    if export_json is not None:
        export_raw = str(export_json).strip()
        export_json = Path(export_raw).expanduser() if export_raw else None
    day_filter = str(get("day_filter", "all")).lower()
    if day_filter not in {"all", "weekday", "weekend", "weekdays", "weekends"}:
        raise ConfigError("day_filter must be all, weekday, or weekend")
    if day_filter == "weekdays":
        day_filter = "weekday"
    if day_filter == "weekends":
        day_filter = "weekend"

    return AnalyzeConfig(
        log_file=log_file,
        year=year,
        min_samples=int(get("min_samples", 2)),
        bin_minutes=int(get("bin_minutes", 30)),
        wake_weight=float(get("wake_weight", 0.5)),
        fragment_weight=float(get("fragment_weight", 0.25)),
        gap_weight=float(get("gap_weight", 0.5)),
        forced_mid_weight=float(get("forced_mid_weight", 0.15)),
        day_filter=day_filter,
        bedtime=bedtime,
        plot=bool(get("plot", False)),
        output_dir=Path(str(get("output_dir", "output"))).expanduser(),
        export_json=export_json,
    )


def load_config(path: str | Path) -> AnalyzeConfig:
    path = Path(path).expanduser()
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")

    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".toml":
        data = _load_toml(text)
    elif suffix == ".json":
        data = _load_json(text)
    else:
        raise ConfigError(
            f"Unsupported config type {path.suffix!r}; use .toml or .json"
        )
    return _coerce(data)


def config_to_dict(config: AnalyzeConfig) -> dict:
    return {
        "log_file": str(config.log_file),
        "year": config.year,
        "min_samples": config.min_samples,
        "bin_minutes": config.bin_minutes,
        "wake_weight": config.wake_weight,
        "fragment_weight": config.fragment_weight,
        "gap_weight": config.gap_weight,
        "forced_mid_weight": config.forced_mid_weight,
        "day_filter": config.day_filter,
        "bedtime": config.bedtime,
        "plot": config.plot,
        "output_dir": str(config.output_dir),
        "export_json": str(config.export_json) if config.export_json else None,
    }


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _to_toml(data: dict) -> str:
    lines = [
        "# SleepAnalyzer config — run with: sleep-analyzer",
        "# CLI flags override these values. See README for keys.",
        "",
    ]
    for key in CONFIG_KEYS:
        if key not in data:
            continue
        value = data[key]
        if value is None:
            lines.append(f"# {key} = ...")
            continue
        if isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, int) and not isinstance(value, bool):
            lines.append(f"{key} = {value}")
        elif isinstance(value, float):
            lines.append(f"{key} = {value}")
        else:
            lines.append(f'{key} = "{_toml_escape(str(value))}"')
    lines.append("")
    return "\n".join(lines)


def save_config(config: AnalyzeConfig, path: str | Path) -> Path:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = config_to_dict(config)
    suffix = path.suffix.lower()
    if suffix == ".toml":
        path.write_text(_to_toml(data), encoding="utf-8")
    elif suffix == ".json":
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    else:
        raise ConfigError(
            f"Unsupported config type {path.suffix!r}; use .toml or .json"
        )
    return path


def argparse_defaults(config: AnalyzeConfig) -> dict:
    return {
        "log_file": str(config.log_file),
        "year": config.year,
        "min_samples": config.min_samples,
        "bin_minutes": config.bin_minutes,
        "wake_weight": config.wake_weight,
        "fragment_weight": config.fragment_weight,
        "gap_weight": config.gap_weight,
        "forced_mid_weight": config.forced_mid_weight,
        "day_filter": config.day_filter,
        "bedtime": config.bedtime,
        "plot": config.plot,
        "output_dir": str(config.output_dir),
        "export_json": str(config.export_json) if config.export_json else None,
    }

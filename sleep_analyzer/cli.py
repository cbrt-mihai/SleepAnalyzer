"""CLI entrypoint for SleepAnalyzer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sleep_analyzer import __version__
from sleep_analyzer.config import (
    AnalyzeConfig,
    ConfigError,
    argparse_defaults,
    default_config,
    find_config_file,
    load_config,
)
from sleep_analyzer.metrics import analyze, filter_nights
from sleep_analyzer.parse import ParseError, parse_file
from sleep_analyzer.plots import generate_plots
from sleep_analyzer.recommend import build_recommendations
from sleep_analyzer.report import render_report


def run_analysis(config: AnalyzeConfig) -> int:
    if config.bin_minutes <= 0:
        print("Error: --bin-minutes must be positive", file=sys.stderr)
        return 1
    if config.min_samples < 1:
        print("Error: --min-samples must be >= 1", file=sys.stderr)
        return 1

    try:
        nights, warnings = parse_file(config.log_file, year=config.year)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ParseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    weights = config.score_weights()
    try:
        filtered = filter_nights(nights, config.day_filter)
        analysis = analyze(
            nights,
            weights=weights,
            bin_minutes=config.bin_minutes,
            min_samples=config.min_samples,
            day_filter=config.day_filter,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        recommendations = build_recommendations(
            filtered,
            analysis,
            weights=weights,
            bin_minutes=config.bin_minutes,
            min_samples=config.min_samples,
            bedtime=config.bedtime,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(render_report(analysis, recommendations, warnings=warnings))

    if config.plot:
        paths = generate_plots(analysis, config.output_dir)
        print(f"Wrote {len(paths)} plot(s) to {config.output_dir}/")
        for path in paths:
            print(f"  {path}")

    if config.export_json:
        out = config.export_json
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "analysis": analysis,
            "recommendations": recommendations,
            "warnings": warnings,
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote JSON report to {out}")

    return 0


def run_validate(log_file: Path, year: int | None) -> int:
    try:
        nights, warnings = parse_file(log_file, year=year)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ParseError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"OK: {len(nights)} night(s) in {log_file}")
    if nights:
        print(
            f"  Range: {nights[0].start.date().isoformat()} → "
            f"{nights[-1].end.date().isoformat()}"
        )
        composite = sum(1 for n in nights if n.is_composite)
        if composite:
            print(f"  Composite nights: {composite}")
    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  • {w}")
        return 0  # valid enough; warnings are non-fatal
    print("No warnings.")
    return 0


def build_analyze_parser(prog: str = "sleep-analyzer") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Analyze sleep logs and recommend optimal bedtime/duration windows.\n\n"
            "Commands:\n"
            "  sleep-analyzer [LOG] [options]   Analyze (default)\n"
            "  sleep-analyzer wizard           Interactive setup\n"
            "  sleep-analyzer add              Append a night/nap to the log\n"
            "  sleep-analyzer validate [LOG]   Parse-check only\n"
            "  sleep-analyzer analyze [LOG]    Same as default analyze\n\n"
            "Config: auto-loads sleep_analyzer.toml/.json (or --config PATH).\n"
            "CLI flags override config values.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to .toml or .json config (default: auto-detect in cwd)",
    )
    p.add_argument(
        "log_file",
        nargs="?",
        default="data/sleep_log.txt",
        help="Path to sleep log (default: data/sleep_log.txt or config)",
    )
    p.add_argument("--year", type=int, default=None, help="Default year for undated lines")
    p.add_argument("--min-samples", type=int, default=2)
    p.add_argument("--bin-minutes", type=int, default=30)
    p.add_argument("--wake-weight", type=float, default=0.5)
    p.add_argument(
        "--fragment-weight",
        type=float,
        default=0.25,
        help="Composite score penalty per extra segment (default: 0.25)",
    )
    p.add_argument(
        "--gap-weight",
        type=float,
        default=0.5,
        help="Composite score penalty per hour of mid-bout gap (default: 0.5)",
    )
    p.add_argument(
        "--forced-mid-weight",
        type=float,
        default=0.15,
        help="Penalty per mid-segment ended by alarm/call/other (default: 0.15)",
    )
    p.add_argument(
        "--day-filter",
        choices=("all", "weekday", "weekend"),
        default="all",
        help="Analyze all nights, weekdays only, or weekends only",
    )
    p.add_argument("--bedtime", type=str, default=None)
    p.add_argument(
        "--plot",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Write PNG charts (--no-plot to disable)",
    )
    p.add_argument("--output-dir", type=str, default="output")
    p.add_argument("--export-json", type=str, default=None)
    return p


def build_parser() -> argparse.ArgumentParser:
    return build_analyze_parser()


def config_from_args(args: argparse.Namespace) -> AnalyzeConfig:
    return AnalyzeConfig(
        log_file=Path(args.log_file),
        year=args.year,
        min_samples=args.min_samples,
        bin_minutes=args.bin_minutes,
        wake_weight=args.wake_weight,
        fragment_weight=args.fragment_weight,
        gap_weight=args.gap_weight,
        forced_mid_weight=args.forced_mid_weight,
        day_filter=args.day_filter,
        bedtime=args.bedtime,
        plot=bool(args.plot),
        output_dir=Path(args.output_dir),
        export_json=Path(args.export_json) if args.export_json else None,
    )


def _load_base_from_argv(argv: list[str]) -> tuple[AnalyzeConfig, Path | None, list[str]]:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default=None)
    pre_args, remaining = pre.parse_known_args(argv)
    if pre_args.config:
        config_path = Path(pre_args.config).expanduser()
    else:
        config_path = find_config_file()
    if config_path is not None:
        try:
            base = load_config(config_path)
        except ConfigError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
    else:
        base = default_config()
    return base, config_path, remaining


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] in {"wizard", "--wizard"}:
        from sleep_analyzer.wizard import run_wizard

        return run_wizard()

    if argv and argv[0] == "add":
        base, config_path, remaining = _load_base_from_argv(argv[1:])
        add_p = argparse.ArgumentParser(prog="sleep-analyzer add")
        add_p.add_argument(
            "--log-file",
            default=str(base.log_file),
            help="Log file to append to",
        )
        add_p.add_argument("--year", type=int, default=base.year)
        add_p.add_argument(
            "--line",
            type=str,
            default=None,
            help="Raw log line to append (skips interactive prompts)",
        )
        add_p.add_argument(
            "--nap",
            action="store_true",
            help="Interactive nap entry",
        )
        add_args = add_p.parse_args(remaining)
        if config_path:
            print(f"(using config: {config_path})", file=sys.stderr)
        from sleep_analyzer.add_entry import run_add_cli

        return run_add_cli(
            Path(add_args.log_file),
            year=add_args.year,
            line=add_args.line,
            nap=add_args.nap,
        )

    if argv and argv[0] == "validate":
        base, config_path, remaining = _load_base_from_argv(argv[1:])
        val_p = argparse.ArgumentParser(prog="sleep-analyzer validate")
        val_p.add_argument(
            "log_file",
            nargs="?",
            default=str(base.log_file),
        )
        val_p.add_argument("--year", type=int, default=base.year)
        val_args = val_p.parse_args(remaining)
        if config_path:
            print(f"(using config: {config_path})", file=sys.stderr)
        return run_validate(Path(val_args.log_file), val_args.year)

    if argv and argv[0] == "analyze":
        argv = argv[1:]

    base, config_path, remaining = _load_base_from_argv(argv)
    parser = build_analyze_parser()
    parser.set_defaults(**argparse_defaults(base))
    args = parser.parse_args(remaining)

    if config_path is not None:
        print(f"(using config: {config_path})", file=sys.stderr)

    return run_analysis(config_from_args(args))

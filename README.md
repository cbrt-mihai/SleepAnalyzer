# SleepAnalyzer

Analyze a personal sleep log to find optimal bedtime, wake time, and duration windows.

## Log format

### Required night line

```text
Weekday Day Month H:MM - H:MM Weekday Day Month - Rating, Wakeups
```

Old lines with only rating + wakeups still work.

### Optional fields (after wakeups)

```text
..., Wakeups[, latency_min][, wake type][, stress][, nap:MIN]
```

| Field | Values | Notes |
|-------|--------|-------|
| Latency | minutes, e.g. `0`, `10`, `25` or `latency:15` | Rough estimate of time to fall asleep — not exact |
| End / wake reason | `alarm`, `natural`, `call`, `other` | How that wake happened (see below) |
| Stress | `1`–`5` (decimals ok) | Evening stress. Prefer `stress:3.5`, or a bare value after wake type |
| Nap | `nap:40` | Daytime nap minutes on that day (rare is fine) |

Typical order for a single stretch: `Wakeups, latency_min, end_reason, stress`.

**Why distinguish `alarm` / `call` / `other` / `natural`?**  
Alarms are planned; calls and other disturbances are unplanned interruptions; natural means you woke on your own. That matters for composite nights where the first stretch may end by alarm or a call, and the later stretch ends naturally.

### Composite / interrupted sleep

Join asleep stretches with `+`. Tag **each** segment with rough latency and end reason in brackets:

```text
Sat 18 Jul 6:00 - 10:00[25/alarm] + 10:20 - 12:00[15/natural] Sat 18 Jul - 5.25, 1, stress:3.5
```

Also valid: `[25, call]`, `[lat:25 end:other]`.

| Piece | Meaning |
|-------|---------|
| Asleep duration | Sum of segments only (gaps excluded) |
| Gap / interruption | Time between segments (here 20m) |
| Per-segment latency | Estimate for falling asleep *on that stretch* |
| Per-segment end reason | Why that stretch ended |
| Night latency | Initial (first segment) latency |
| Night wake type | Final segment’s end reason |
| Midpoint | First bedtime → final wake |

If brackets are omitted on a multi-segment night, night-level latency applies to the first stretch and night-level wake reason to the last.

### Separate nap lines

```text
Nap Sat 18 Jul 15:30 - 16:00
```

Attached to the night that ends (or starts) on that calendar day. Prefer this when the nap is easy to timestamp; use `nap:MIN` on the night line when you only remember length.

### Examples

```text
Mon 13 Jul 4:05 - 11:15 Mon 13 Jul - 7.25, 0, 5, natural, 2
Tue 14 Jul 3:40 - 9:45 Tue 14 Jul - 6, 0, 20, alarm, 3
Sat 18 Jul 6:00 - 10:00[25/call] + 10:20 - 12:00[15/natural] Sat 18 Jul - 5.25, 1, stress:4
Nap Sun 19 Jul 15:10 - 15:40
Sun 19 Jul 4:48 - 12:00 Sun 19 Jul - 6, 1, 10, natural, 2
```

- Month may be abbreviated (`Jul`) or full (`July`)
- Times are 24-hour (`H:MM` or `HH:MM`)
- Lines starting with `#` are ignored
- Year is optional on each date: `Mon 13 Jul 2026 4:05 - ...`. If omitted, `--year` / config `year` is used; when the calendar goes backwards (e.g. Dec → Jan) the next year is inferred automatically.

Sample data: [`data/sleep_log.txt`](data/sleep_log.txt)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

This installs the `sleep-analyzer` command and dependencies (`numpy`, `matplotlib`).

Alternatively: `pip install -r requirements.txt` and run via `python -m sleep_analyzer` or `python analyze_sleep.py` without installing the console script.

## Usage

### Config file (recommended for everyday runs)

Edit [`sleep_analyzer.toml`](sleep_analyzer.toml) (or `sleep_analyzer.json`) in the project directory, then:

```bash
sleep-analyzer
```

Auto-detected names (first match wins): `sleep_analyzer.toml`, `sleep_analyzer.json`, `config.toml`, `config.json`.

Or point at a file:

```bash
sleep-analyzer --config path/to/my_settings.toml
```

CLI flags always override the config. Example config:

```toml
log_file = "data/sleep_log.txt"
year = 2026
min_samples = 2
bin_minutes = 30
wake_weight = 0.5
fragment_weight = 0.25
gap_weight = 0.5
forced_mid_weight = 0.15
day_filter = "all"          # all | weekday | weekend
# bedtime = "4:30"
plot = false
output_dir = "output"
# export_json = "output/report.json"
```

| Key | Meaning |
|-----|---------|
| `log_file` | Path to the sleep log |
| `year` | Default year for undated log lines |
| `min_samples` | Minimum nights per ranked bin |
| `bin_minutes` | Bin width for time/duration groups |
| `wake_weight` | Score penalty per wakeup |
| `fragment_weight` | Composite: penalty per extra segment |
| `gap_weight` | Composite: penalty per hour of mid-bout gap |
| `forced_mid_weight` | Composite: penalty per mid end via alarm/call/other |
| `day_filter` | `all`, `weekday`, or `weekend` |
| `bedtime` | Optional `H:MM` for cycle wake suggestions |
| `plot` | `true` / `false` — write PNG charts |
| `output_dir` | Chart directory |
| `export_json` | Optional path for JSON report |

On Python 3.10, reading `.toml` needs `tomli` (`pip install tomli`). `.json` works with the stdlib only. Python 3.11+ reads TOML natively.

### Commands

```bash
sleep-analyzer                  # analyze using config
sleep-analyzer wizard           # guided setup (+ optional save config)
sleep-analyzer add              # interactively append a night or nap
sleep-analyzer add --line "Mon 13 Jul 4:05 - 11:15 Mon 13 Jul - 7, 0"
sleep-analyzer validate         # parse-check only (no full report)
sleep-analyzer --day-filter weekday
sleep-analyzer --no-plot

python -m sleep_analyzer
pytest                          # run unit tests (pip install pytest)
```

### Direct CLI flags

```bash
sleep-analyzer data/sleep_log.txt --year 2026 --min-samples 2 --bin-minutes 30
sleep-analyzer data/sleep_log.txt --bedtime 4:30 --plot --export-json output/report.json
sleep-analyzer --fragment-weight 0.3 --gap-weight 0.5 --forced-mid-weight 0.15
```

## Flags

### `--year YEAR`

Assigns a calendar year to every log line (dates in the file have no year).

**Default:** the current system year.

**When to use:**
- Always set this if your log is from a past year, or if you run the tool near New Year’s and entries might be mis-dated.
- Example: analyzing July 2025 data in 2026 → `--year 2025`
- Example: a log that spans Dec–Jan needs one run per year segment, or split the file; the parser can bump wake into the next year for overnight Dec→Jan within a single `--year`, but mixed-year logs are safer split.

```bash
python analyze_sleep.py data/sleep_log.txt --year 2026
```

### `--min-samples N`

A bedtime / wake / duration / midpoint **bin** only appears in rankings if it contains at least `N` nights. Stops one-off great (or terrible) nights from looking like a pattern.

**Default:** `2`

**When to use:**
- Early log (under ~2 weeks): keep `2`, or try `1` if almost every bin is empty — treat results as exploratory.
- Larger log (30+ nights): raise to `3` or `4` so recommendations need repeated evidence.

```bash
# Show singleton nights in bins (noisy, useful when n is tiny)
python analyze_sleep.py data/sleep_log.txt --min-samples 1

# Stricter: only trust windows seen at least 3 times
python analyze_sleep.py data/sleep_log.txt --min-samples 3
```

### `--bin-minutes MINUTES`

Width of grouping windows for clock times and duration. Bedtime `4:05` and `4:25` both fall in `04:00–04:30` when the bin is 30 minutes. Duration bins use the same width converted to hours (30 → 0.5h).

**Default:** `30`

**When to use:**
- Coarse pattern with little data → `60` (fewer, fuller bins).
- Fine-grained schedule once you have lots of nights → `15`.
- Too many empty bins → increase; everything collapsed into one bin → decrease.

```bash
python analyze_sleep.py data/sleep_log.txt --bin-minutes 60
python analyze_sleep.py data/sleep_log.txt --bin-minutes 15
```

### `--wake-weight WEIGHT`

Defines the base quality score used for ranking:

```text
score = rating − wake_weight × wakeups
```

**Default:** `0.5` (each wakeup subtracts half a rating point).

**When to use:**
- Wakeups bother you a lot → raise (e.g. `1.0` so one wakeup costs a full rating point).
- You care mostly about how you feel in the morning → lower (e.g. `0.25`) or `0` to rank by rating alone.

```bash
sleep-analyzer --wake-weight 1.0
sleep-analyzer --wake-weight 0
```

### `--fragment-weight` / `--gap-weight` / `--forced-mid-weight`

Extra composite-night penalties (see Quality score). Defaults `0.25` / `0.5` / `0.15`.

### `--day-filter {all,weekday,weekend}`

Analyze only weekdays, only weekends, or everything (default `all`). Useful when social jet lag is large.

```bash
sleep-analyzer --day-filter weekday
```

### `--bedtime H:MM`

Candidate bedtime for **tonight-style** cycle suggestions. Prints wake times for ~90-minute sleep cycles from that bedtime. Preferred cycle count is taken from your best historical cycle bin when available.

**Default:** unset. If omitted, the report still suggests wake options using the midpoint of your best bedtime window (when one exists).

**When to use:**
- You already know when you’ll try to sleep and want wake targets.
- Comparing two candidate bedtimes in separate runs (`4:00` vs `5:00`).

```bash
python analyze_sleep.py data/sleep_log.txt --bedtime 4:30
python analyze_sleep.py data/sleep_log.txt --bedtime 5:00
```

### `--plot` / `--no-plot`

Writes PNG charts under `--output-dir` (bedtime/duration vs rating, bin bars, weekday vs weekend, rolling trend). Use `--no-plot` to override `plot = true` in a config file.

**Default:** off (unless set in config).

**When to use:**
- You want visuals for patterns that tables understate (clusters, outliers, trends).
- Sharing or journaling results. Requires `matplotlib` (`pip install -r requirements.txt`).

```bash
python analyze_sleep.py data/sleep_log.txt --plot
```

### `--output-dir DIR`

Directory for plot PNGs when `--plot` is set.

**Default:** `output`

**When to use:**
- Keep dated snapshots: `--output-dir output/2026-07`
- Avoid overwriting a previous chart set.

```bash
python analyze_sleep.py data/sleep_log.txt --plot --output-dir output/week29
```

### `--export-json PATH`

Writes the full analysis payload (summary, bins, correlations, recommendations, per-night records, parse warnings) as JSON.

**Default:** unset (no file).

**When to use:**
- Feed another tool, notebook, or dashboard.
- Diff week-over-week machine-readable results.
- Debug why a recommendation appeared.

```bash
python analyze_sleep.py data/sleep_log.txt --export-json output/report.json
```

## Quality score

**Continuous night**

```text
score = rating − wake_weight × wakeups
```

**Composite night** (more than one segment) also subtracts small penalties (configurable):

```text
score = rating − wake_weight × wakeups
        − fragment_weight × (segments − 1)
        − gap_weight × (gap hours)
        − forced_mid_weight × (forced mid-ends)
```

Defaults: `0.25`, `0.5`, `0.15`. Set them in the config file or via `--fragment-weight`, `--gap-weight`, `--forced-mid-weight`.

## Understanding the output

The terminal report is printed top to bottom in these sections.

### Header summary

```text
Nights: 7  |  Range: 2026-07-13 → 2026-07-19
Duration: mean …  median …  std …
Rating:   mean …  median …  std …
Wakeups:  mean …  median …  std …
Score:    mean …  (rating − 0.5 × wakeups)
```

| Field | Meaning |
|-------|---------|
| Nights / Range | How many entries parsed and the first→last calendar span |
| Duration | How long you slept (from bedtime to wake), in hours |
| Rating | Your logged subjective quality |
| Wakeups | Interruptions per night |
| Score | Composite used for ranking (see above) |
| mean / median / std | Center and spread; high std means inconsistent nights |

### Parse warnings

Shown only if lines failed to parse, nights look out of order, or entries overlap. Fix the log line or pass the correct `--year`.

### Recommendations

```text
Confidence: low|moderate|reasonable  (n=…)
Best bedtime window:  …
Best duration window: …
Best wake window:     …
Target duration:      … (cycle-aligned ≈ …)
Best cycle count:     …
If you go to bed at …:
  → wake … (N cycles / …h) ← preferred
```

| Field | Meaning |
|-------|---------|
| Confidence | `low` under 14 nights, `moderate` under 30, else `reasonable` — sample-size honesty, not a medical claim |
| Best bedtime / duration / wake windows | Highest mean-score bin that met `--min-samples` |
| Target duration | Mean duration inside the best duration bin (or overall mean if needed) |
| Cycle-aligned | Nearest multiple of ~90 minutes to that target |
| Best cycle count | Whole-cycle bucket (4, 5, 6, …) with the best mean score |
| If you go to bed at… | Cycle-based wake options; `← preferred` marks the historically stronger cycle length |
| `!` lines | Caveats: small n, social jet lag, worsening/improving trend, empty strict bins |

**How to act on it:** pick a bedtime window that scores well *and* you can keep on weekdays; aim for the cycle-aligned duration; use the wake list when you set an alarm from a known bedtime.

### Sleep debt / balance

Compares each night’s asleep duration to the **target duration** (best duration-bin mean). Cumulative balance sums (duration − target); negative means you are short of that target over time. Also shows the last-7-night balance.

### Bin tables (bedtime, duration, wake, midpoint)

```text
Window             n   score  rating  wakeups    dur
04:30–05:00        2    6.00    6.50     1.00  6.47h
```

| Column | Meaning |
|--------|---------|
| Window | Time or duration range for that bin |
| n | Nights in the bin |
| score / rating / wakeups | Means inside the bin |
| dur | Mean sleep length of nights in that bin |

Tables are sorted by score (then n). Empty tables mean no bin reached `--min-samples`.

### Sleep midpoint (why it matters)

**Sleep midpoint** is the clock time halfway between bedtime and wake. If you sleep `4:00 → 10:00`, the midpoint is `7:00`.

```text
bedtime -------- midpoint -------- wake
  4:00              7:00            10:00
```

It answers a different question than bedtime or wake alone:

| Measure | Question it answers |
|---------|---------------------|
| Bedtime | When did you start trying to sleep? |
| Wake time | When did the night end? |
| Duration | How long was the night? |
| Midpoint | Where did the *whole night* sit on the 24-hour clock? |

**Why not just use bedtime?** Two nights can share a bedtime but land in very different places circadian-wise:

- `3:30 → 8:30` → midpoint `6:00`, duration 5h  
- `3:30 → 11:30` → midpoint `7:30`, duration 8h  

Same bedtime, different “biological night.” Midpoint captures that shift.

**Why not just use wake time?** Wake is often constrained by alarms, work, or weekends. Midpoint blends start and end, so it better reflects your actual sleep timing habit.

**What midpoint bins are good for:**

1. **Finding your best “sleep placement”** — which part of the morning/night your sleep centered on when scores were highest (e.g. midpoint `07:30–08:00` vs `09:00–09:30`).
2. **Consistency** — a stable midpoint usually means a stable body clock; a large midpoint std means your nights keep sliding around.
3. **Social jet lag** — weekend midpoint minus weekday midpoint. A +1–2h weekend delay is common and often linked to worse Monday feel, even if weekend duration looks fine.
4. **Separating “late schedule” from “short sleep”** — if late midpoints score poorly but short-duration bins also score poorly, you may have two issues; if only late midpoints look bad while duration bins look fine, timing/placement is the stronger suspect.

**How to use it with the other bins:** use bedtime/wake bins to set a concrete schedule (alarms, wind-down). Use midpoint bins and social jet lag to check whether that schedule keeps your whole night from drifting later on weekends.

### Bedtime × duration grid

Cells that combine a bedtime bin with a duration bin (only if that pair has enough nights). Answers: “Is 4:30–5:00 *with* 7–7.5h better than the same bedtime with shorter sleep?” Often empty until the log grows.

### Consistency / social jet lag

| Field | Meaning |
|-------|---------|
| Bedtime / midpoint / duration std | How much those vary night to night (higher = less consistent) |
| Weekday vs weekend midpoint | Average sleep midpoint on weekdays vs Sat/Sun (by wake day) |
| Social jet lag | Weekend midpoint minus weekday midpoint, in hours; flagged if the absolute shift is over 1 hour |

A large positive jet lag usually means later weekend nights. That can drag weekday ratings even if weekend duration looks fine.

### Factors (optional fields)

Shown when enough nights include labels (`--min-samples` applies per group):

| Block | Meaning |
|-------|---------|
| By latency (initial) | Buckets for first-stretch latency (0–5, 6–15, 16–30, 31+ min) |
| By final wake / end reason | Final stretch: alarm / natural / call / other |
| By mid-segment end reason | How *non-final* stretches ended (composite nights) |
| By stress | Groups for stress 1–5 |
| By nap | Nights with any nap minutes vs none |
| By continuity | Continuous vs composite nights |

Coverage counts in the header show how many nights have each optional field filled in.

### Correlations

Pearson `r` between pairs of measures. Range roughly −1…+1. Labels in the report:

| Label | What it is |
|-------|------------|
| `duration` | Asleep length in hours (sum of segments) |
| `time in bed` | First bed → final wake (includes gaps) |
| `interruption min` | Gap minutes between segments |
| `bedtime` | Clock time you went to bed (later = larger) |
| `wake time` | Clock time you woke (later = larger) |
| `sleep midpoint` | Halfway between first bed and final wake |
| `wakeups` | Times woken (your count) |
| `stress` | Evening stress 1–5 (when logged) |
| `latency min` | Estimated minutes to fall asleep (when logged) |
| `rating` | Your subjective quality |
| `score` | `rating − wake_weight × wakeups` |

How to read `r`:

- Near **+1**: they rise together.
- Near **−1**: one rises as the other falls.
- Near **0**: little linear relationship in *this* sample.

**Important caveats:**

- Correlation is not causation.
- Some pairs are linked by math, not biology — e.g. `rating ↔ score` is almost always very high because score is built from rating. `bedtime ↔ sleep midpoint` and `wake time ↔ sleep midpoint` are also often high because midpoint is computed from those times.
- With a short log, treat strong-looking `r` cautiously (needs at least 3 nights with variance).

**Pairs worth attention** (once you have more data): `duration ↔ rating`, `sleep midpoint ↔ rating` / `score`, `wakeups ↔ rating`, `bedtime ↔ rating`. Strong `wake time ↔ sleep midpoint` mostly confirms that later wakes pull the night later — useful context, not a new insight by itself.

### Trend

Compares the earlier half of the log to the later half:

- **improving** / **worsening** / **stable** from rating change
- **rating Δ** and **duration Δ**: late mean minus early mean

Useful to see whether recent weeks are drifting, not just what the all-time average says.

### Best / worst nights

Top and bottom nights by score, with times, duration, rating, and wakeups — concrete examples of what “good” and “bad” looked like for you.

### All nights

Full table of every parsed night (bed, wake, duration, rating, wakeups, score, midpoint). Use it to spot typos or verify a surprising bin.

### Plots (`--plot`)

| File | Contents |
|------|----------|
| `bedtime_vs_rating.png` | Scatter of bedtime vs rating (color ≈ score) |
| `duration_vs_rating.png` | Duration vs rating (color ≈ wakeups) |
| `bedtime_bins.png` / `duration_bins.png` / `wake_bins.png` | Mean score per bin |
| `weekday_weekend.png` | Rating histograms by weekday vs weekend |
| `rolling_trend.png` | Nightly rating plus rolling rating/duration |

### JSON (`--export-json`)

Machine-readable mirror of the analysis: `analysis` (summary, bins, grid, consistency, correlations, rolling series, trend, extremes, nights, params), `recommendations`, and `warnings`. Same numbers as the terminal report, structured for reuse.

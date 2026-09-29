"""Dựng dashboard 6 panel từ data/logs.jsonl theo contract config/dashboard.yaml.

Ví dụ:
    python scripts/build_dashboard.py --out submission/evidence/11-dashboard-overview.png
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio
from app.metrics import percentile

# Reference palette (dataviz skill), light mode.
SURFACE = "#fcfcfb"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"]
THRESHOLD = "#52514e"


def load_records(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        record["_ts"] = datetime.fromisoformat(record["ts"].replace("Z", "+00:00"))
        records.append(record)
    return records


def minute(ts: datetime) -> datetime:
    return ts.replace(second=0, microsecond=0)


def compute(records: list[dict], window_end: datetime, window_minutes: int) -> dict:
    window_start = window_end - timedelta(minutes=window_minutes)
    in_window = [r for r in records if window_start <= r["_ts"] <= window_end]
    received = [r for r in in_window if r.get("event") == "request_received"]
    sent = [r for r in in_window if r.get("event") == "response_sent"]
    failed = [r for r in in_window if r.get("event") == "request_failed"]
    tool_events = [r for r in in_window if r.get("tool_success") is not None]

    per_minute: dict[datetime, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for r in received:
        per_minute[minute(r["_ts"])]["received"].append(1)
    for r in failed:
        per_minute[minute(r["_ts"])]["failed"].append(1)
    for r in tool_events:
        per_minute[minute(r["_ts"])]["tool"].append(bool(r["tool_success"]))
    for r in sent:
        bucket = per_minute[minute(r["_ts"])]
        for field in ("latency_ms", "ttft_ms", "cost_usd", "tokens_in", "tokens_out", "quality_score"):
            if r.get(field) is not None:
                bucket[field].append(r[field])

    latencies = [r["latency_ms"] for r in sent]
    ttfts = [r["ttft_ms"] for r in sent if r.get("ttft_ms") is not None]
    return {
        "window_start": window_start,
        "window_end": window_end,
        "per_minute": dict(sorted(per_minute.items())),
        "summary": {
            "requests": len(received),
            "responses": len(sent),
            "failed": len(failed),
            "latency_p50": percentile(latencies, 50),
            "latency_p95": percentile(latencies, 95),
            "latency_p99": percentile(latencies, 99),
            "ttft_p95": percentile(ttfts, 95),
            "error_rate_pct": round(100 * len(failed) / len(received), 2) if received else 0.0,
            "error_breakdown": dict(Counter(r.get("error_type") for r in failed)),
            "retrieval_success_pct": round(
                100 * sum(bool(r["tool_success"]) for r in tool_events) / len(tool_events), 2
            ) if tool_events else 0.0,
            "cost_total_usd": round(sum(r.get("cost_usd") or 0 for r in sent), 6),
            "tokens_in_total": sum(r.get("tokens_in") or 0 for r in sent),
            "tokens_out_total": sum(r.get("tokens_out") or 0 for r in sent),
            "quality_mean": round(mean(r["quality_score"] for r in sent), 3) if sent else 0.0,
        },
    }


def style_axis(ax, title: str, unit: str, subtitle: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color=TEXT_PRIMARY, pad=22)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=8.5, color=TEXT_SECONDARY, va="bottom")
    ax.set_ylabel(unit, color=TEXT_SECONDARY, fontsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, labelsize=8)


def time_axis(ax, data: dict) -> None:
    ax.set_xlim(data["window_start"], data["window_end"])
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=range(0, 60, 10)))


def threshold_line(ax, value: float, label: str) -> None:
    ax.axhline(value, color=THRESHOLD, linestyle=(0, (4, 3)), linewidth=1.2)
    ax.annotate(label, xy=(0, value), xycoords=("axes fraction", "data"), xytext=(4, 3),
                textcoords="offset points", ha="left", va="bottom", fontsize=8, color=TEXT_SECONDARY)


def line(ax, xs, ys, slot: int, label: str) -> None:
    ax.plot(xs, ys, color=SERIES[slot], linewidth=2, marker="o", markersize=4, label=label)


def legend(ax) -> None:
    ax.legend(loc="upper right", fontsize=8, frameon=False, ncol=4, labelcolor=TEXT_SECONDARY)


def render(data: dict, contract: dict, out: Path, title_suffix: str, mark: datetime | None = None) -> None:
    panels = {p["id"]: p for p in contract["dashboard"]["panels"]}
    pm = data["per_minute"]
    s = data["summary"]
    xs = list(pm.keys())

    fig, axes = plt.subplots(3, 2, figsize=(15, 12), facecolor=SURFACE)
    start = data["window_start"].strftime("%Y-%m-%d %H:%M")
    end = data["window_end"].strftime("%H:%M UTC")
    fig.suptitle(
        f"{contract['dashboard']['title']}{title_suffix}\n"
        f"Time range: last {contract['dashboard']['time_range_minutes']} min ({start} → {end}) · "
        f"refresh {contract['dashboard']['refresh_seconds']}s · source data/logs.jsonl · "
        f"{s['requests']} requests",
        x=0.01, ha="left", fontsize=12, color=TEXT_PRIMARY,
    )

    # 1. Latency
    ax = axes[0][0]
    p = panels["latency"]
    lat_x = [m for m in xs if pm[m].get("latency_ms")]
    for slot, (label, q) in enumerate((("P50", 50), ("P95", 95), ("P99", 99))):
        line(ax, lat_x, [percentile(pm[m]["latency_ms"], q) for m in lat_x], slot, label)
    line(ax, lat_x, [percentile(pm[m]["ttft_ms"], 95) for m in lat_x], 3, "TTFT P95")
    threshold_line(ax, p["threshold"]["value"], f"SLO P95 ≤ {p['threshold']['value']} ms")
    style_axis(ax, p["title"], p["unit"],
               f"P50 {s['latency_p50']:.0f} · P95 {s['latency_p95']:.0f} · P99 {s['latency_p99']:.0f} · "
               f"TTFT P95 {s['ttft_p95']:.0f} ms")
    top = max([p["threshold"]["value"]] + [s["latency_p99"]])
    ax.set_ylim(0, top * 1.3)
    legend(ax)
    time_axis(ax, data)

    # 2. Traffic
    ax = axes[0][1]
    p = panels["traffic"]
    ax.bar(xs, [len(pm[m].get("received", [])) for m in xs], width=1 / 1440 * 0.8, color=SERIES[0],
           label="requests/min")
    threshold_line(ax, p["threshold"]["value"], f"min {p['threshold']['value']} req/min")
    style_axis(ax, p["title"], "requests / min", f"Total {s['requests']} requests trong cửa sổ")
    time_axis(ax, data)

    # 3. Errors + retrieval success
    ax = axes[1][0]
    p = panels["errors"]
    err_x = [m for m in xs if pm[m].get("received")]
    line(ax, err_x, [100 * len(pm[m].get("failed", [])) / len(pm[m]["received"]) for m in err_x], 1,
         "error rate %")
    tool_x = [m for m in xs if pm[m].get("tool")]
    line(ax, tool_x, [100 * sum(pm[m]["tool"]) / len(pm[m]["tool"]) for m in tool_x], 0,
         "retrieval success %")
    threshold_line(ax, p["threshold"]["value"], f"error rate ≤ {p['threshold']['value']}%")
    breakdown = ", ".join(f"{k}={v}" for k, v in s["error_breakdown"].items()) or "none"
    style_axis(ax, p["title"], p["unit"],
               f"Error rate {s['error_rate_pct']}% · retrieval success {s['retrieval_success_pct']}% · "
               f"errors: {breakdown}")
    ax.set_ylim(-3, 120)
    legend(ax)
    time_axis(ax, data)

    # 4. Cost
    ax = axes[1][1]
    p = panels["cost"]
    cost_x = [m for m in xs if pm[m].get("cost_usd")]
    per_min = [sum(pm[m]["cost_usd"]) for m in cost_x]
    ax.bar(cost_x, per_min, width=1 / 1440 * 0.8, color=SERIES[0], label="cost / min")
    cumulative, running = [], 0.0
    for value in per_min:
        running += value
        cumulative.append(running)
    line(ax, cost_x, cumulative, 1, "cumulative")
    threshold_line(ax, p["threshold"]["value"], f"budget ≤ ${p['threshold']['value']}")
    style_axis(ax, p["title"], "USD", f"Total ${s['cost_total_usd']:.4f} trong cửa sổ")
    ax.set_yscale("symlog", linthresh=0.01)
    ax.set_ylim(0, p["threshold"]["value"] * 8)
    legend(ax)
    time_axis(ax, data)

    # 5. Tokens
    ax = axes[2][0]
    p = panels["tokens"]
    names = ["tokens_in", "tokens_out"]
    values = [s["tokens_in_total"], s["tokens_out_total"]]
    bars = ax.barh(names, values, color=[SERIES[0], SERIES[1]], height=0.5)
    for bar, value in zip(bars, values):
        ax.annotate(f"{value:,}", xy=(bar.get_width(), bar.get_y() + bar.get_height() / 2), xytext=(4, 0),
                    textcoords="offset points", va="center", fontsize=9, color=TEXT_PRIMARY)
    ax.axvline(p["threshold"]["value"], color=THRESHOLD, linestyle=(0, (4, 3)), linewidth=1.2)
    ax.annotate(f"limit ≤ {p['threshold']['value']:,} / field", xy=(p["threshold"]["value"], 1.3),
                xytext=(-4, 0), textcoords="offset points", ha="right", fontsize=8, color=TEXT_SECONDARY)
    style_axis(ax, p["title"], "", f"Sum theo field trong cửa sổ (unit: {p['unit']})")
    ax.set_xlim(0, p["threshold"]["value"] * 1.1)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.grid(axis="y", visible=False)

    # 6. Quality
    ax = axes[2][1]
    p = panels["quality"]
    q_x = [m for m in xs if pm[m].get("quality_score")]
    line(ax, q_x, [mean(pm[m]["quality_score"]) for m in q_x], 2, "mean quality")
    threshold_line(ax, p["threshold"]["value"], f"min {p['threshold']['value']}")
    style_axis(ax, p["title"], p["unit"], f"Mean {s['quality_mean']}")
    ax.set_ylim(0, 1.05)
    time_axis(ax, data)

    if mark is not None:
        for ax in (axes[0][0], axes[0][1], axes[1][0], axes[1][1], axes[2][1]):
            ax.axvline(mark, color=TEXT_PRIMARY, linewidth=1, linestyle=":")
            ax.annotate(f"incident start {mark:%H:%M:%S}", xy=(mark, 1), xycoords=("data", "axes fraction"),
                        xytext=(-4, -12), textcoords="offset points", ha="right", fontsize=8, color=TEXT_PRIMARY)

    fig.tight_layout(rect=(0, 0, 1, 0.955), h_pad=3)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=110, facecolor=SURFACE)


def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs", type=Path, default=REPO_ROOT / "data" / "logs.jsonl")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "config" / "dashboard.yaml")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "submission" / "evidence" / "11-dashboard-overview.png")
    parser.add_argument("--end", help="ISO UTC cuối cửa sổ; mặc định là log mới nhất")
    parser.add_argument("--title-suffix", default="")
    parser.add_argument("--mark", help="ISO UTC: vẽ vạch đánh dấu thời điểm incident bắt đầu")
    args = parser.parse_args()

    contract = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    records = load_records(args.logs)
    if not records:
        raise SystemExit("Không có log để dựng dashboard")
    end = (datetime.fromisoformat(args.end.replace("Z", "+00:00")) if args.end
           else max(r["_ts"] for r in records)) + timedelta(seconds=30)
    data = compute(records, end.astimezone(timezone.utc), contract["dashboard"]["time_range_minutes"])
    mark = datetime.fromisoformat(args.mark.replace("Z", "+00:00")) if args.mark else None
    render(data, contract, args.out, args.title_suffix, mark)
    print(json.dumps(data["summary"], ensure_ascii=False, indent=1))
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()

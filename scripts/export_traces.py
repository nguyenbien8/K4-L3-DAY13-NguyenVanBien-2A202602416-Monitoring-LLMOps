"""Xuất tóm tắt trace từ Langfuse (API v2 observations) để làm evidence, bỏ các field chứa key."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import configure_utf8_stdio

FIELDS = "core,basic,metadata,model,usage,prompt,metrics"
SAFE_METADATA_PREFIXES = ("scope.", "resourceAttributes.")


def fetch(start: str, end: str) -> list[dict]:
    auth = (os.environ["LANGFUSE_PUBLIC_KEY"], os.environ["LANGFUSE_SECRET_KEY"])
    base = os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com").rstrip("/")
    rows: list[dict] = []
    cursor = None
    while True:
        params = {"fromStartTime": start, "toStartTime": end, "limit": 100, "fields": FIELDS}
        if cursor:
            params["cursor"] = cursor
        response = httpx.get(f"{base}/api/public/v2/observations", auth=auth, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        rows.extend(payload.get("data", []))
        cursor = (payload.get("meta") or {}).get("cursor")
        if not cursor:
            return rows


def clean_metadata(metadata: dict | None) -> dict:
    return {k: v for k, v in (metadata or {}).items() if not k.startswith(SAFE_METADATA_PREFIXES)}


def main() -> None:
    configure_utf8_stdio()
    load_dotenv(REPO_ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="start", required=True, help="ISO UTC, ví dụ 2026-09-29T08:00:00Z")
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--correlation-id", action="append", default=[], help="Chỉ in chi tiết các ID này")
    args = parser.parse_args()

    traces: dict[str, list[dict]] = defaultdict(list)
    for row in fetch(args.start, args.end):
        traces[row["traceId"]].append(row)

    print(f"Langfuse traces trong khoảng {args.start} → {args.end}: {len(traces)}")
    print(f"{'trace_id':34} {'correlation_id':14} {'start (UTC)':24} {'root_ms':>7} observations")
    ordered = sorted(traces.items(), key=lambda item: min(o["startTime"] for o in item[1]))
    for trace_id, observations in ordered:
        root = next((o for o in observations if o.get("isRootObservation")), observations[0])
        cid = clean_metadata(root.get("metadata")).get("correlation_id", "-")
        types = ",".join(o["type"] for o in sorted(observations, key=lambda o: o["startTime"]))
        print(f"{trace_id:34} {cid:14} {root['startTime']:24} {int((root.get('latency') or 0) * 1000):>7} {types}")
        if cid not in args.correlation_id:
            continue
        for obs in sorted(observations, key=lambda o: (not o.get("isRootObservation"), o["startTime"])):
            relation = "ROOT" if obs.get("isRootObservation") else f"child of {obs['parentObservationId']}"
            print(f"    - {obs['type']:10} {obs['name']:14} {relation:28} {int((obs.get('latency') or 0) * 1000)}ms level={obs.get('level')}")
            if obs["type"] == "GENERATION":
                print(f"        model={obs.get('model')} prompt={obs.get('promptName')} v{obs.get('promptVersion')}"
                      f" usage={obs.get('usageDetails')} cost={obs.get('costDetails')} ttft_s={obs.get('timeToFirstToken')}")
            print(f"        metadata={json.dumps(clean_metadata(obs.get('metadata')), ensure_ascii=False)}")


if __name__ == "__main__":
    main()

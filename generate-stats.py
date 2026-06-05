#!/usr/bin/env python3
"""Generate live-stats.json from local Claude session files and push to atlas."""

import glob
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLAUDE_SESSIONS = str(Path.home() / ".claude" / "projects" / "**" / "*.jsonl")
CLAUDE_STATS    = Path.home() / ".claude" / "stats-cache.json"
OUT_FILE        = Path(__file__).parent / "live-stats.json"
ATLAS_DEST      = "atlas:~/services/ai-dashboard/live-stats.json"

CLAUDE_PRICING = {
    "claude-sonnet-4-6":         {"input": 3.0,  "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-opus-4-7":           {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75},
    "claude-opus-4-6":           {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0,  "cache_read": 0.08, "cache_write": 1.0},
}


def parse_sessions(days=30):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    daily = {}
    model_totals = {}

    for path in glob.glob(CLAUDE_SESSIONS, recursive=True):
        try:
            with open(path, errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    if d.get("type") != "assistant":
                        continue
                    msg = d.get("message", {})
                    usage = msg.get("usage", {})
                    if not usage:
                        continue
                    model = msg.get("model", "unknown")
                    if model in ("<synthetic>", "unknown"):
                        continue
                    ts = d.get("timestamp", 0)
                    if isinstance(ts, str):
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    else:
                        dt = datetime.fromtimestamp(ts / 1000 if ts > 1e10 else ts, tz=timezone.utc)
                    date = dt.strftime("%Y-%m-%d")

                    # Daily chart (last N days only)
                    if dt >= cutoff:
                        entry = daily.setdefault(date, {})
                        entry[model] = entry.get(model, 0) + usage.get("output_tokens", 0)

                    # All-time model totals
                    mt = model_totals.setdefault(model, {
                        "inputTokens": 0, "outputTokens": 0,
                        "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0,
                    })
                    mt["inputTokens"]              += usage.get("input_tokens", 0)
                    mt["outputTokens"]             += usage.get("output_tokens", 0)
                    mt["cacheReadInputTokens"]     += usage.get("cache_read_input_tokens", 0)
                    mt["cacheCreationInputTokens"] += usage.get("cache_creation_input_tokens", 0)
        except Exception:
            pass

    # Compute API value per model
    total_value = 0.0
    for model, mt in model_totals.items():
        p = CLAUDE_PRICING.get(model, {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75})
        value = (
            mt["inputTokens"]              / 1e6 * p["input"] +
            mt["outputTokens"]             / 1e6 * p["output"] +
            mt["cacheReadInputTokens"]     / 1e6 * p["cache_read"] +
            mt["cacheCreationInputTokens"] / 1e6 * p["cache_write"]
        )
        mt["api_value_usd"] = round(value, 2)
        total_value += value

    # Fall back to stats-cache for model totals if sessions gave nothing
    if not model_totals and CLAUDE_STATS.exists():
        cache = json.loads(CLAUDE_STATS.read_text())
        model_totals = cache.get("modelUsage", {})
        for model, mt in model_totals.items():
            p = CLAUDE_PRICING.get(model, {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75})
            value = (
                mt.get("inputTokens", 0)              / 1e6 * p["input"] +
                mt.get("outputTokens", 0)             / 1e6 * p["output"] +
                mt.get("cacheReadInputTokens", 0)     / 1e6 * p["cache_read"] +
                mt.get("cacheCreationInputTokens", 0) / 1e6 * p["cache_write"]
            )
            mt["api_value_usd"] = round(value, 2)
            total_value += value

    # Load activity counts from stats-cache
    activity = {}
    if CLAUDE_STATS.exists():
        cache = json.loads(CLAUDE_STATS.read_text())
        activity = {
            "totalSessions": cache.get("totalSessions", 0),
            "totalMessages": cache.get("totalMessages", 0),
        }

    return {
        "dailyModelTokens": [{"date": d, "tokensByModel": daily[d]} for d in sorted(daily)],
        "modelUsage": model_totals,
        "total_api_value": round(total_value, 2),
        "generated_at": datetime.now().isoformat(),
        **activity,
    }


if __name__ == "__main__":
    stats = parse_sessions()
    OUT_FILE.write_text(json.dumps(stats))
    subprocess.run(["rsync", "-q", str(OUT_FILE), ATLAS_DEST], check=True)
    print(f"Pushed {len(stats['dailyModelTokens'])} days, "
          f"{len(stats['modelUsage'])} models, "
          f"${stats['total_api_value']:.2f} API value → atlas")

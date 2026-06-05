#!/usr/bin/env python3
"""AI Usage Dashboard — aggregates token usage across Claude, OpenAI, Grok, and Ollama."""

import glob
import json
import os
import threading
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

BASE = Path(__file__).parent
CONFIG_FILE = BASE / "config.json"
CLAUDE_STATS = Path.home() / ".claude" / "stats-cache.json"
CLAUDE_SESSIONS = str(Path.home() / ".claude" / "projects" / "**" / "*.jsonl")

CLAUDE_PRICING = {
    "claude-sonnet-4-6":         {"input": 3.0,  "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-opus-4-7":           {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75},
    "claude-opus-4-6":           {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0,  "cache_read": 0.08, "cache_write": 1.0},
}

DEFAULT_CONFIG = {
    "name": "Drew",
    "subscriptions": [
        {"id": "claude_pro",   "label": "Claude Pro",      "provider": "Anthropic", "monthly_cost": 20,  "color": "#00e599"},
        {"id": "chatgpt_plus", "label": "ChatGPT Plus",   "provider": "OpenAI",    "monthly_cost": 20,  "color": "#74aa9c"},
        {"id": "grok_super",   "label": "Super Grok",     "provider": "xAI",       "monthly_cost": 30,  "color": "#1da1f2"},
        {"id": "codex",        "label": "Codex CLI",      "provider": "OpenAI",    "monthly_cost": 0,   "color": "#74aa9c"},
        {"id": "ollama",       "label": "Ollama (Local)", "provider": "Local",     "monthly_cost": 0,   "color": "#a78bfa"},
    ],
    "api_keys": {"openai": "", "xai": ""},
    "ollama_host": "http://localhost:11434",
}


def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
    return DEFAULT_CONFIG.copy()


def get_claude_data():
    if not CLAUDE_STATS.exists():
        return {}
    data = json.loads(CLAUDE_STATS.read_text())
    model_usage = data.get("modelUsage", {})
    total_value = 0.0
    enriched = {}
    for model, usage in model_usage.items():
        p = CLAUDE_PRICING.get(model, {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75})
        value = (
            usage.get("inputTokens", 0)              / 1e6 * p["input"] +
            usage.get("outputTokens", 0)             / 1e6 * p["output"] +
            usage.get("cacheReadInputTokens", 0)     / 1e6 * p["cache_read"] +
            usage.get("cacheCreationInputTokens", 0) / 1e6 * p["cache_write"]
        )
        total_value += value
        enriched[model] = {**usage, "api_value_usd": round(value, 2)}
    data["modelUsage"] = enriched
    data["total_api_value"] = round(total_value, 2)
    return data


def get_daily_from_sessions(days=30):
    """Parse session jsonl files for per-day, per-model token counts."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    daily = {}
    for path in glob.glob(CLAUDE_SESSIONS, recursive=True):
        try:
            with open(path, errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or '"type":"assistant"' not in line and '"type": "assistant"' not in line:
                        continue
                    d = json.loads(line)
                    if d.get("type") != "assistant":
                        continue
                    msg = d.get("message", {})
                    usage = msg.get("usage", {})
                    if not usage:
                        continue
                    ts = d.get("timestamp", 0)
                    dt = datetime.fromtimestamp(ts / 1000 if ts > 1e10 else ts, tz=timezone.utc)
                    if dt < cutoff:
                        continue
                    date = dt.strftime("%Y-%m-%d")
                    model = msg.get("model", "unknown")
                    if model == "<synthetic>":
                        continue
                    entry = daily.setdefault(date, {})
                    entry[model] = entry.get(model, 0) + usage.get("output_tokens", 0)
        except Exception:
            pass
    return [{"date": d, "tokensByModel": daily[d]} for d in sorted(daily)]


def get_ollama_data(host):
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=2) as r:
            data = json.loads(r.read())
        models = data.get("models", [])
        return {"status": "online", "count": len(models), "models": models}
    except Exception as e:
        return {"status": "offline", "count": 0, "models": [], "error": str(e)}


def get_openai_usage(api_key):
    if not api_key:
        return None
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        req = urllib.request.Request(
            f"https://api.openai.com/v1/usage?date={today}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return {"status": "ok", "data": json.loads(r.read())}
    except Exception as e:
        return {"status": "error", "error": str(e)}


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/data":
            cfg = load_config()
            claude = get_claude_data()
            ollama = get_ollama_data(cfg.get("ollama_host", "http://localhost:11434"))
            openai_key = cfg.get("api_keys", {}).get("openai", "")

            claude_cost = next(
                (s["monthly_cost"] for s in cfg.get("subscriptions", []) if s["id"] == "claude_pro"), 0
            )
            total_monthly = sum(s["monthly_cost"] for s in cfg.get("subscriptions", []))
            api_savings = round(claude.get("total_api_value", 0) - claude_cost, 2)

            # Replace stale cached daily data with live session data
            claude["dailyModelTokens"] = get_daily_from_sessions()

            payload = {
                "name": cfg.get("name", "User"),
                "subscriptions": cfg.get("subscriptions", []),
                "total_monthly_cost": total_monthly,
                "api_savings": api_savings,
                "claude": claude,
                "ollama": ollama,
                "openai_usage": get_openai_usage(openai_key),
                "generated_at": datetime.now().isoformat(),
            }
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    port = 7474
    server = HTTPServer(("0.0.0.0", port), Handler)
    url = f"http://localhost:{port}"
    print(f"\n  AI Dashboard → {url}\n  Ctrl+C to stop\n")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")

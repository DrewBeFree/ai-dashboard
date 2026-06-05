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
    # Prefer pre-computed live-stats.json (pushed by generate-stats.py on the host machine)
    live = BASE / "live-stats.json"
    if live.exists():
        return json.loads(live.read_text())
    # Fall back to stats-cache.json + local session parsing
    data = json.loads(CLAUDE_STATS.read_text()) if CLAUDE_STATS.exists() else {}
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


def get_xai_usage(api_key):
    if not api_key:
        return None
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # xAI usage endpoint (OpenAI-compatible style)
        req = urllib.request.Request(
            f"https://api.x.ai/v1/usage?date={today}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            return {"status": "ok", "data": json.loads(r.read())}
    except urllib.error.HTTPError as e:
        # If /usage doesn't exist, verify key with /models
        if e.code in (404, 405):
            try:
                req2 = urllib.request.Request(
                    "https://api.x.ai/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                with urllib.request.urlopen(req2, timeout=5) as r:
                    models = [m.get("id") for m in json.loads(r.read()).get("data", [])]
                    return {"status": "key_only", "models": models,
                            "note": "Usage endpoint not available via API — check console.x.ai"}
            except Exception as e2:
                return {"status": "error", "error": str(e2)}
        return {"status": "error", "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_gemini_usage(api_key, project_id):
    """Fetch today's Gemini usage via the AI Studio usage API."""
    if not api_key:
        return None
    try:
        # List models to verify key is valid
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}&pageSize=5",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
        models = [m.get("name","").replace("models/","") for m in data.get("models", [])]
        return {"status": "ok", "key_valid": True, "models": models[:5],
                "note": "Credit usage requires GCP OAuth — check console.cloud.google.com",
                "project": project_id}
    except Exception as e:
        return {"status": "error", "error": str(e)}


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
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/config":
            self._send_json(load_config())
            return
        if self.path == "/api/data":
            cfg = load_config()
            claude = get_claude_data()
            ollama = get_ollama_data(cfg.get("ollama_host", "http://localhost:11434"))
            openai_key  = cfg.get("api_keys", {}).get("openai", "")
            gemini_key  = cfg.get("api_keys", {}).get("gemini", "")
            xai_key     = cfg.get("api_keys", {}).get("xai", "")
            gcp_project = cfg.get("gcp_project", "")

            claude_cost = next(
                (s["monthly_cost"] for s in cfg.get("subscriptions", []) if s["id"] == "claude_pro"), 0
            )
            total_monthly = sum(s["monthly_cost"] for s in cfg.get("subscriptions", []))
            api_savings = round(claude.get("total_api_value", 0) - claude_cost, 2)

            payload = {
                "name": cfg.get("name", "User"),
                "subscriptions": cfg.get("subscriptions", []),
                "total_monthly_cost": total_monthly,
                "api_savings": api_savings,
                "claude": claude,
                "ollama": ollama,
                "openai_usage": get_openai_usage(openai_key),
                "gemini_usage": get_gemini_usage(gemini_key, gcp_project),
                "xai_usage": get_xai_usage(xai_key),
                "gcp_credits": cfg.get("gcp_credits", []),
                "generated_at": datetime.now().isoformat(),
            }
            self._send_json(payload)
        else:
            super().do_GET()

    def do_POST(self) -> None:
        if self.path != "/api/config":
            self.send_error(404)
            return
        try:
            length  = int(self.headers.get("Content-Length", 0))
            updates = json.loads(self.rfile.read(length))
            cfg     = load_config()

            for k, v in updates.items():
                if k == "api_keys" and isinstance(v, dict):
                    cfg.setdefault("api_keys", {}).update(v)
                elif k == "subscriptions" and isinstance(v, list):
                    by_id = {s["id"]: s for s in cfg.get("subscriptions", [])}
                    for s in v:
                        if s["id"] in by_id:
                            by_id[s["id"]]["monthly_cost"] = s["monthly_cost"]
                    cfg["subscriptions"] = list(by_id.values())
                else:
                    cfg[k] = v

            CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
            self._send_json({"ok": True})
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)})

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

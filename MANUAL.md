# AI Dashboard — Manual

## Overview

AI Dashboard is a Python web server that aggregates token usage and subscription cost data across all AI providers into a single dark-themed SPA. It runs on **atlas** (PowerEdge R720xd) as a systemd user service and is accessible from anywhere on Tailscale at `http://atlas:7474`.

Live Claude stats are generated on **AlienWare** every 30 minutes by `generate-stats.py`, which parses local session files and rsyncs the output to atlas.

## Architecture

```
AlienWare (cron every 30 min)
  generate-stats.py
    ├── globs ~/.claude/projects/**/*.jsonl
    ├── parses ISO-timestamp assistant messages
    ├── computes dailyModelTokens, modelUsage, total_api_value
    └── rsyncs → atlas:~/services/ai-dashboard/live-stats.json

atlas:~/services/ai-dashboard/
  app.py  (Python http.server on 0.0.0.0:7474)
    ├── GET  /              → serves index.html
    ├── GET  /api/data      → JSON payload (reads live-stats.json, config.json, queries Ollama/OpenAI/xAI/Gemini)
    ├── GET  /api/config    → returns current config.json
    └── POST /api/config    → merges and saves config.json updates

  index.html  (Chart.js 4.4.0 + vanilla JS)
    ├── Overview  — metric cards, daily stacked bar chart, model doughnut, subscription table, provider sections
    ├── Activity  — 30-day token chart, sessions/messages/API value cards, daily breakdown table
    └── Settings  — editable form for name, subscription costs, API keys, Ollama host, GCP project
```

## Data Sources

### Claude (primary: `live-stats.json`)
`generate-stats.py` runs on AlienWare and parses `~/.claude/projects/**/*.jsonl`. Each assistant message contains per-model token usage in snake_case fields (`output_tokens`, `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`). Timestamps are ISO strings.

Output JSON:
- `dailyModelTokens` — last 30 days of per-model output tokens
- `modelUsage` — all-time per-model token counts + computed `api_value_usd`
- `total_api_value` — total API-equivalent value across all models
- `totalSessions`, `totalMessages` — pulled from `stats-cache.json` fallback

Fallback: if `live-stats.json` is absent or stale, `app.py` falls back to `~/.claude/stats-cache.json` (Claude Code's own cache file).

### Ollama (`ollama_host` in config.json)
Queries `/api/tags`. Returns installed model names, families, and sizes.

### OpenAI (`api_keys.openai` in config.json)
Optional. Queries `/v1/usage?date=TODAY`. Returns per-model token counts for today.

### xAI / Grok (`api_keys.xai` in config.json)
Optional. Tries `/v1/usage?date=TODAY` first; falls back to `/v1/models` for key validation. No usage endpoint is currently available via xAI's public API — usage must be checked at console.x.ai.

### Gemini / GCP (`api_keys.gemini` + `gcp_project` in config.json)
Optional. Validates key via `/v1beta/models`. Full credit/usage data requires GCP OAuth — credits are tracked manually in `config.json` under `gcp_credits`.

### Subscriptions (manual)
Defined in `config.json`. Monthly costs are edited via the Settings view or directly in the file. No billing API is queried.

## API Value Calculation

Claude Pro and Max are flat subscriptions — the API usage value is the equivalent cost if you had paid per-token:

| Model | Input | Output | Cache Read | Cache Write |
|---|---|---|---|---|
| claude-sonnet-4-6 | $3.00/M | $15.00/M | $0.30/M | $3.75/M |
| claude-opus-4-7 | $15.00/M | $75.00/M | $1.50/M | $18.75/M |
| claude-haiku-4-5-20251001 | $0.80/M | $4.00/M | $0.08/M | $1.00/M |

**API Savings** = total API value − Claude Pro monthly cost. Positive = subscription is worth it.

## Deployment (atlas)

The server runs as a systemd user service:

```
~/.config/systemd/user/ai-dashboard.service
```

Commands:
```bash
systemctl --user start ai-dashboard
systemctl --user stop ai-dashboard
systemctl --user restart ai-dashboard
systemctl --user status ai-dashboard
```

Service starts automatically on boot (`enabled`). The process runs `app.py` from `~/services/ai-dashboard/` and serves on port 7474.

## Live Stats Cron (AlienWare)

```
*/30 * * * * python3 ~/ai-dashboard/generate-stats.py >> /tmp/ai-dashboard-sync.log 2>&1
```

`generate-stats.py` writes `live-stats.json` locally and rsyncs it to `atlas:~/services/ai-dashboard/live-stats.json`.

## Configuration Reference

`config.json` lives only on atlas at `~/services/ai-dashboard/config.json` (gitignored). Edit via the Settings view in the dashboard or with `ssh atlas nano ~/services/ai-dashboard/config.json`.

```json
{
  "name": "Drew",
  "subscriptions": [
    {"id": "claude_pro",   "label": "Claude Pro",      "provider": "Anthropic", "monthly_cost": 20,  "color": "#00e599"},
    {"id": "chatgpt_plus", "label": "ChatGPT Plus",    "provider": "OpenAI",    "monthly_cost": 20,  "color": "#74aa9c"},
    {"id": "grok_super",   "label": "Super Grok",      "provider": "xAI",       "monthly_cost": 30,  "color": "#1da1f2"},
    {"id": "codex",        "label": "Codex CLI",       "provider": "OpenAI",    "monthly_cost": 0,   "color": "#74aa9c"},
    {"id": "ollama",       "label": "Ollama (Local)",  "provider": "Local",     "monthly_cost": 0,   "color": "#a78bfa"},
    {"id": "gemini",       "label": "Gemini (GCP)",    "provider": "Google",    "monthly_cost": 0,   "color": "#4285f4"}
  ],
  "api_keys": {
    "openai": "sk-...",
    "xai":    "xai-...",
    "gemini": ""
  },
  "ollama_host": "http://localhost:11434",
  "gcp_project": "your-project-id",
  "gcp_credits": [
    {"name": "Trial credit", "remaining": 1000, "original": 1000, "expires": "May 21, 2027", "status": "Available"}
  ]
}
```

## Updating Pricing

Edit `CLAUDE_PRICING` in both `app.py` and `generate-stats.py` if Anthropic changes rates.

## Status

| Component | Status |
|---|---|
| Claude stats (live session files) | Working — 30-day window, updated every 30 min |
| Ollama model list | Working |
| OpenAI usage API | Working (requires key) |
| xAI/Grok key validation | Working; usage endpoint not available via API |
| Gemini key validation | Working; credit tracking via config.json |
| Activity view | Working |
| Settings view (UI config editor) | Working — saves to config.json on atlas |
| Persistent long-term history | Not implemented (SQLite would extend beyond 30 days) |

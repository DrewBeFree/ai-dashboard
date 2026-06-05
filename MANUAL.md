# AI Dashboard — Manual

## Overview

AI Dashboard is a local Python web server that aggregates token usage and subscription cost data across all AI providers into a single dark-themed web UI. It runs entirely on your machine with no cloud dependencies.

## Architecture

```
app.py (Python http.server)
  ├── GET /          → serves index.html
  ├── GET /api/data  → returns JSON payload
  │     ├── reads ~/.claude/stats-cache.json (Claude token data)
  │     ├── queries http://localhost:11434/api/tags (Ollama)
  │     └── queries OpenAI Usage API (if key configured)
  └── GET /config.json, etc → static file serving

index.html (Chart.js + vanilla JS)
  └── fetches /api/data → renders cards, charts, tables
```

## Data Sources

### Claude Code (`~/.claude/stats-cache.json`)
Auto-written by Claude Code. Contains:
- `modelUsage` — per-model cumulative token counts (input, output, cache_read, cache_write)
- `dailyModelTokens` — last ~10 days of per-model totals
- `dailyActivity` — message and session counts per day
- `totalSessions`, `totalMessages` — all-time counts

### Ollama (`http://localhost:11434`)
Queries `/api/tags` on startup. Returns installed model names, families, and sizes.

### OpenAI Usage API
Optional. Requires an API key in `config.json`. Queries `/v1/usage?date=TODAY`. Returns token counts for the current day.

### Subscriptions (manual)
Configured in `config.json`. Monthly costs are entered manually — no billing API is queried.

## API Value Calculation

Since Claude Max is a flat subscription, `costUSD` in the stats file is always `0`. The dashboard calculates API-equivalent value using current per-token pricing:

| Model | Input | Output | Cache Read | Cache Write |
|---|---|---|---|---|
| claude-sonnet-4-6 | $3.00/M | $15.00/M | $0.30/M | $3.75/M |
| claude-opus-4-7 | $15.00/M | $75.00/M | $1.50/M | $18.75/M |
| claude-haiku-4-5-20251001 | $0.80/M | $4.00/M | $0.08/M | $1.00/M |

**API Savings** = total API value − Claude Max monthly cost. A positive number means your subscription is worth more than what you'd pay per-token.

## Running

```bash
python3 ~/ai-dashboard/app.py
```

No pip installs needed — stdlib only (`http.server`, `json`, `urllib.request`, `threading`).

Dashboard auto-opens at `http://localhost:7474`. Ctrl+C to stop.

## Configuration Reference

`config.json` is auto-created on first run with defaults. Edit to customize:

```json
{
  "name": "Drew",
  "subscriptions": [
    {
      "id":           "claude_max",
      "label":        "Claude Max 20x",
      "provider":     "Anthropic",
      "monthly_cost": 200,
      "color":        "#00e599"
    }
  ],
  "api_keys": {
    "openai": "sk-...",
    "xai":    ""
  },
  "ollama_host": "http://localhost:11434"
}
```

## Updating Pricing

Edit `CLAUDE_PRICING` in `app.py` if Anthropic changes rates.

## Limitations

- Claude stats only cover what's cached locally — typically the last ~10 days (Claude Code recomputes periodically)
- No persistent storage — the dashboard reads live data on each `/api/data` request
- OpenAI usage endpoint returns today only; historical data requires separate calls per date
- Grok/xAI has no public usage API yet — cost is manual-entry only

## Status

| Component | Status |
|---|---|
| Claude stats (local) | Working |
| Ollama model list | Working |
| OpenAI usage API | Working (requires key) |
| xAI/Grok usage | Not available (manual cost only) |
| Persistent history | Not implemented |

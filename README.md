# AI Dashboard

A local web dashboard for tracking token usage and subscription costs across all your AI providers.

## What It Tracks

| Provider | Data Source | Usage | Cost |
|---|---|---|---|
| Claude (Anthropic) | `~/.claude/stats-cache.json` | Tokens by model, daily breakdown, API-equivalent value | Subscription vs API savings |
| OpenAI / ChatGPT | OpenAI Usage API (optional) | Token usage if API key provided | Manual monthly entry |
| Super Grok (xAI) | Manual | — | Manual monthly entry |
| Codex CLI | Manual | — | Manual monthly entry |
| Ollama (local) | `http://localhost:11434/api/tags` | Model list | Free |

## Quick Start

```bash
cd ~/ai-dashboard
python3 app.py
```

Opens at `http://localhost:7474`. Ctrl+C to stop.

## Configuration

Edit `config.json` to set your subscription costs and API keys:

```json
{
  "name": "Drew",
  "subscriptions": [
    {"id": "claude_max", "label": "Claude Max 20x", "provider": "Anthropic", "monthly_cost": 200},
    ...
  ],
  "api_keys": {
    "openai": "sk-..."
  },
  "ollama_host": "http://localhost:11434"
}
```

API keys are optional — the dashboard works without them, just using local Claude data and manual subscription entries.

## Features

- **Monthly Spend** — total across all subscriptions
- **API Value** — what your Claude usage would cost at API rates (shows subscription ROI)
- **Daily Token Chart** — stacked bar chart by model over the past ~10 days
- **Model Distribution** — doughnut chart of token share by model
- **Claude Model Table** — per-model output tokens, cache reads, and API value
- **Subscription Table** — all services with provider and monthly cost
- **Ollama Status** — online/offline with installed model list

## Files

```
app.py        Python server (no external deps, stdlib only)
index.html    Dashboard frontend (Chart.js via CDN)
config.json   Subscription costs and API keys (auto-created on first run)
```

## Notes

- Claude stats only reflect what's in `~/.claude/stats-cache.json` — typically the last ~10 days
- `costUSD` in the stats file is always `0` on subscription plans; the dashboard calculates API-equivalent value using current pricing
- Ollama queries `localhost:11434` — adjust `ollama_host` in config if you run it on another port

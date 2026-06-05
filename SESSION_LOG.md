# Session Log

## 2026-06-05 — Activity + Settings views

**What we did:**
- Added Activity view: full-width 30-day token chart, summary cards (total sessions/messages/API value), daily breakdown table with per-model badges
- Added Settings view: editable form for display name, subscription monthly costs, API keys (OpenAI/xAI/Gemini) with show/hide toggle, Ollama host, GCP project ID
- Added `GET /api/config` — returns current `config.json` to populate the settings form
- Added `POST /api/config` — merges and saves updates (handles subscriptions list and api_keys dict specially to avoid clobbering unlisted keys)
- Extracted `_send_json()` helper in `Handler` to remove duplication
- Nav links (Activity, Settings) are now fully wired with `switchView()` JS

**Where we stopped:**
- All three nav views fully functional and deployed to atlas
- Settings changes persist to `config.json` on atlas and take effect on next Overview refresh

**Next up:**
- GCP credits are still manually maintained in `config.json` — could add a credits editing section to Settings
- Consider adding SQLite history for long-term session tracking beyond 30 days

## 2026-06-05 — Initial build

**What we did:**
- Created `app.py` — stdlib-only Python server with `/api/data` endpoint reading Claude stats, Ollama, and optional OpenAI usage API
- Created `index.html` — dark-themed dashboard with Chart.js: metric cards, daily stacked bar chart, model doughnut, subscription table, Ollama model grid
- Set up git repo on `main` branch
- Wrote README, MANUAL, SESSION_LOG, DETAILS

**Where we stopped:**
- Dashboard is functional; config.json auto-generates on first run
- OpenAI usage API wired but untested (needs real key)
- xAI/Grok has no usage API — manual cost entry only

**Next up:**
- Add OpenAI API key to config.json and verify usage data pulls correctly
- Consider adding persistent history (SQLite) so stats extend beyond Claude's 10-day cache window
- Add xAI usage API if/when it becomes available
- Consider adding a `/api/config` PUT endpoint so settings can be edited from the UI

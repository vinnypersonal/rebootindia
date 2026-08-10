# RebootIndia — Autonomous Social-Accountability Engine

Identifies, verifies, and posts real public-problem accountability campaigns for
[rebootindia.com](https://rebootindia.com) — national issues first, naming the responsible
authority and pairing every problem with a concrete solution. Fully autonomous, ₹0 runtime.

Full spec: [`CLAUDE.md`](./CLAUDE.md) — the source of truth for this build. This README is
the quick-start; if the two ever disagree, `CLAUDE.md` wins.

## How it works

```
Trend Scout / News Discovery (code, ₹0)
        │
        ▼
Worker — 1 Model Router call, 4 personas (Researcher, Fact-Checker, Strategist, Solutions Architect)
        │
        ▼
Reviewer — Pass A (deterministic checks) + Pass B (2nd Model Router call, fact-support verify)
        │ (bounce → 1 retry via Worker → re-review; still failing → drop that platform)
        ▼
Poster — X / Facebook / Instagram (only platforms marked ready=true)
        │
        ▼
Logger + SQLite state (data/state.db, committed by the Action)
```

Every single post, every platform, every run passes through the Reviewer before it can
publish. Nothing bypasses that gate to save quota — volume drops before review coverage does.

## Repository layout

See `CLAUDE.md` §5. Key entry point: `src/director.py`, invoked as
`python -m src.director --mode {new-problems|trend-scan|follow-ups|growth-review} [--dry-run]`.

## Local setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m src.director --mode trend-scan --dry-run   # safe: no posting keys required
```

`--dry-run` (or leaving the `REBOOT_LIVE_POSTING` repo variable unset in Actions) runs the
full generate-and-review pipeline but never calls a posting API — this is the default until
the CEO explicitly flips it live.

## Required GitHub Actions Secrets (only needed for live posting / live LLM calls)

| Secret | Used for |
|---|---|
| `GEMINI_API_KEY` | Model Router priority 1 |
| `GROQ_API_KEY` | Model Router priority 2 |
| `CEREBRAS_API_KEY` | Model Router priority 3 |
| `MISTRAL_API_KEY` | Model Router priority 4 |
| `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` | X/Twitter posting (OAuth1.0a user context) |
| `FB_PAGE_ID`, `FB_PAGE_ACCESS_TOKEN` | Facebook Page posting |
| `IG_USER_ID`, `IG_ACCESS_TOKEN` | Instagram posting (Business/Creator account linked to the Page) |

Repo variable `REBOOT_LIVE_POSTING=true` switches the 3h/hourly/daily workflows from
dry-run to live. Leave it unset until the CEO signs off (`CLAUDE.md` §12).

## Status vs. `CLAUDE.md` v2 backlog (§11)

Built (T1–T12): repo scaffold, config/domains/cities/handles, SQLite store, GDELT + Google
News RSS discovery, Google Trends + GDELT-spike Trend Scout, Model Router (Gemini → Groq →
Cerebras → Mistral failover), 4-persona Worker, 2-pass Reviewer, X/Facebook/Instagram
posters, Director orchestration with `--dry-run`, follow-up flow that re-fetches fresh news
and re-runs the full pipeline with the original post attached as context (a status check, not
a repeat report), the 4 GitHub Actions crons, and a unit test suite (27 tests,
`python -m unittest discover -s tests`).

Not yet built, on purpose:
- **T4b** — X's actual current free-tier write cap has not been probed live (no X credentials
  in this environment). `config.DAILY_CAMPAIGN_CAP` defaults to 40 per the doc; **re-verify
  against X's real cap before going live** and lower the config value to match if needed.
- **T13** (`growth.py`) — Phase 2 engagement read-back is a stub by design (CLAUDE.md marks
  it Phase 2). It logs and exits; it does not yet bias domain/city selection.
- **T14** — no rebootindia.com publish hook yet.

## Decisions still pending CEO sign-off (`CLAUDE.md` §12)

1. **Repo visibility** — must be public for unlimited free GitHub Actions minutes.
2. **Daily campaign ceiling** — defaults to 40; confirm once X's real write cap is probed (T4b).
3. **Satire ratio cap** — defaults to 20% (`config.SATIRE_MAX_RATIO`).
4. **Priority city/district pool** — seeded with ~60 major cities in `data/cities.yaml`; CEO
   may override the list or the selection method.
5. **State store** — SQLite in-repo (default, already built) vs. a Google Sheets dashboard.
6. **Model Router provider order** — default Gemini → Groq → Cerebras → Mistral; get free-tier
   keys for all four before enabling live posting.

**Also required before going live:** the Instagram/Facebook/X one-time human account &
Developer App setup — Meta's and X's consent screens need the CEO personally; no CLI can do
that step. Ministry/office handles in `data/handles.yaml` and `data/domains.yaml` are
deliberately left blank rather than guessed (Reviewer Pass A enforces this) — fill in verified
official handles before going live.

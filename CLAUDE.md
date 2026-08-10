# CLAUDE.md — RebootIndia Autonomous Command Center (v2)

> Operating brief for Claude Code. Read fully at the start of every session.
> Repo: https://github.com/vinnypersonal/rebootindia.git
> Companion doc: `RebootIndia-Command-Center.md` (v1 architecture rationale — superseded in
> parts by this file; this file wins on any conflict).
> v2 changelog: added Reviewer/Verifier stage, trending-topic detection, Instagram, a
> validated (not literal) frequency plan, satire guardrails, growth strategy.

---

## 1. Identity & Mission

**Project:** RebootIndia autonomous social-accountability engine for rebootindia.com
**Owner:** CEO, RebootIndia (NGO)
**Mission:** Identify, expose, and help solve real public problems across India — national
problems first and foremost — naming the responsible authority for each and always pairing
the problem with a concrete solution.

**Editorial stance:** factual, patriotic, pro-development, accountability-focused. Problem +
Solution, never problem alone. Primary focus: all-India / Central-government-level issues.
District/city content is secondary volume, rotated in around the national core.

---

## 2. Prime Directives (non-negotiable)

1. **Zero variable cost.** Every runtime dependency must be a free tier. No paid API on a
   schedule. Flag and stop rather than silently add a paid service.
2. **Fully autonomous runtime.** Runs on schedule, no human in the loop for operation.
3. **Nothing posts unreviewed.** Every single post — all three platforms, every run — passes
   through the Reviewer/Verifier stage (§6) before it is allowed to publish. No exceptions,
   including trending/satire posts.
4. **Accuracy is the shield.** If a claim is not clearly supported by the source, that
   platform's post is dropped (`ready=false`). Never fabricate numbers, quotes, or events.
   Satire is exempt from "literal" but never from "fact-anchored" (§8).
5. **Accountability trail.** Every post names/tags the responsible ministry/department/office
   and carries the source URL.
6. **Claude Code is the builder, not the runtime.** The deployed system thinks with the free
   runtime LLM (Gemini Flash), never by calling Claude on a schedule.
7. **Sustainable, not maximal, volume.** "Post as much as possible" means "maximize within
   what keeps the account healthy and inside free tiers" — not literal saturation. See §7.

---

## 3. Architecture v2 — Five Sub-Agents + a Model Router

The Director remains pure code (₹0). What's new in v2: a Trend Scout (code, ₹0), a Reviewer
(a second, separate LLM call — still ₹0 on free tiers, but it doubles LLM usage per post,
accounted for in §7's volume math), and a **Model Router** — every place this doc says
"Gemini Flash call," read it as "Model Router call" (§3a). No single free-tier provider is
trusted alone.

```
┌─────────────────────────────────────────────────────────────────┐
│ DIRECTOR (Python rules — ₹0)                                     │
│  Runs every 3h (new problems) + hourly (trend scan) + daily      │
│  (follow-ups + growth review). Picks next task(s), routes, logs. │
└───────────────┬───────────────────────────────────────────────┘
                │
   ┌────────────▼─────────────┐     ┌─────────────────────────────┐
   │ TREND SCOUT (code — ₹0)   │     │ NEWS DISCOVERY (code — ₹0)    │
   │ Hourly.                   │     │ GDELT DOC API, country=IN     │
   │ - Google Trends India RSS │     │ + Google News RSS fallback    │
   │   (free, no key)          │     │ Pulls title, url, snippet,    │
   │ - GDELT volume-spike per  │     │ image where available         │
   │   tracked domain keyword  │     └───────────────┬───────────────┘
   │ Inserts HIGH-priority     │                     │
   │ trend tasks into queue,   │                     │
   │ deduped vs last 24h       │                     │
   └────────────┬──────────────┘                     │
                └──────────────┬─────────────────────┘
                               │ article (+ maybe trend tag)
                ┌──────────────▼─────────────────────────────────┐
                │ WORKER — ONE Gemini Flash call, 4 personas:      │
                │  1 Researcher    → problem + responsible office  │
                │  2 Fact-Checker  → verify vs source, HIGH        │
                │      PRECISION, ready=false if unsupported       │
                │  3 Strategist    → TW/FB/IG posts, tags, regional│
                │      language, hashtags (trending + evergreen),  │
                │      occasional satire per §8                    │
                │  4 Solutions Architect → one concrete solution   │
                │ Returns ONE JSON between ##REBOOT_START/END##    │
                └──────────────┬───────────────────────────────────┘
                               │ draft post JSON
                ┌──────────────▼───────────────────────────────────┐
                │ REVIEWER / VERIFIER (§6)                          │
                │  Pass A — deterministic code checks (₹0):         │
                │    platform limits, required fields, handle       │
                │    format, source URL resolves (HTTP 200), image  │
                │    present if Instagram, banned-phrase screen      │
                │  Pass B — second Gemini Flash call (₹0, separate  │
                │    from Worker): "does this post assert anything  │
                │    the source doesn't support?" → approve / bounce│
                │  On bounce: ONE regeneration retry via Worker with│
                │  the issue appended; if it fails again, drop that │
                │  platform's post for this run (log why).          │
                └──────────────┬───────────────────────────────────┘
                               │ approved posts only
                ┌──────────────▼───────────────────────────────────┐
                │ POSTER (code — ₹0): X API + FB Graph + IG Graph    │
                └──────────────┬───────────────────────────────────┘
                               │
                ┌──────────────▼───────────────────────────────────┐
                │ LOGGER + GROWTH TRACKER (code — ₹0)                │
                │ Logs everything; schedules follow-up (+7d);        │
                │ (Phase 2) reads back engagement metrics to bias    │
                │ future domain/city selection — see §11             │
                └────────────────────────────────────────────────────┘
```

**Cost accounting per campaign:** 1 Worker call + up to 2 Reviewer calls (approve + one retry
worst case) = up to 3 LLM calls, routed through §3a. All free tier. This is why §7 sizes
daily volume against the *pooled* free-tier headroom, not just one provider's cap.

---

### 3a. Model Router — multi-provider fallback (no single point of failure)

Free-tier LLM limits move without notice — one provider alone is a liability, not a
convenience. `model_router.py` wraps all LLM calls (Worker and Reviewer alike) behind one
function, tries providers in priority order, and fails over automatically on a 429/error/
timeout. All four candidates below expose an OpenAI-compatible chat-completions endpoint, so
one adapter shape covers all of them — only the base URL, model name, and API key differ.

| Priority | Provider | Model | Free limit (verify at build time — these shift monthly) |
|---|---|---|---|
| 1 (primary) | Google Gemini | Gemini 2.5 Flash | ~15 RPM / ~1,500 RPD (cut 50–80% in late 2025 — re-check at T0) |
| 2 (fallback) | Groq | Llama 3.3 70B | 30 RPM / 1,000 RPD / 100K tokens/day — fast, no card |
| 3 (fallback) | Cerebras | Llama/Qwen (check current catalog) | ~1M tokens/day |
| 4 (fallback) | Mistral | Mistral Small/Large | ~1B tokens/month (most generous by volume, but treat as the least-tested of the four here) |

Routing logic: try priority 1 → on failure/429 log the failover and try 2 → 3 → 4 in order.
Log which provider actually served every call (`logs.llm_provider` column) so the daily
volume math in §7 and any future "our free ceiling shrank" diagnosis has real data, not
guesses. If ALL four are exhausted in a run, skip that campaign and log it — never silently
fall back to a paid call.

**Experimental last-resort (Phase 3, optional, not required for launch):** CPU inference of
a small open-weight model (e.g., Qwen2.5-3B-Instruct, quantized) run directly inside the
GitHub Actions job via llama.cpp — genuinely zero external dependency, but slow (~30–90s per
call) and lower quality. Given Prime Directive 4 (accuracy is the shield), do not use this
tier for the Reviewer's Pass B fact-check — only ever as a Worker-side last resort when all
four hosted providers are down, and flag any post generated this way for the CEO to spot-check.

---

## 4. Free-Tier Stack (updated)

| Layer | Choice | Cost | Notes |
|---|---|---|---|
| Scheduler / runtime | GitHub Actions (cron) | ₹0 | **Repo must be public** for unlimited free minutes; private repos get a small free minutes/month cap — confirm repo visibility at T1 |
| News discovery | GDELT DOC API | ₹0 | No key, 15-min refresh, country=IN, includes `socialimage` field |
| News fallback | Google News RSS | ₹0 | Unofficial |
| Trending source | **Google Trends India daily RSS** — `trends.google.com/trends/trendingsearches/daily/rss?geo=IN` | ₹0 | Official free feed, no key |
| Trending fallback | GDELT article-volume spike per tracked keyword (last 1h vs 24h avg) | ₹0 | Pure math on GDELT data already being pulled |
| Runtime LLM | **Model Router** (§3a): Gemini Flash → Groq → Cerebras → Mistral, in order | ₹0 | Pooled free-tier headroom; no single provider is trusted alone |
| Posting: X/Twitter | X API v2 free tier | ₹0 | **Verify current write cap at build time** — historically volatile, treat as the binding ceiling across all platforms |
| Posting: Facebook | Meta Graph API (Page token) | ₹0 | |
| Posting: Instagram | Meta Instagram Graph API | ₹0 | One-time human setup, see v1 doc §4 — Business/Creator account + linked Page + Dev App, Development Mode (own account only) avoids App Review |
| State store | SQLite file in repo (or JSON) | ₹0 | Committed back by the Action |
| Secrets | GitHub Actions Secrets | ₹0 | Never commit keys |

X's real free-tier posting cap is not something to assume — Claude Code should write a small
probe/read-limits step early (T4b) and report the actual number back before the volume config
in §7 is finalized live.

---

## 5. Repository Layout (target — matches vinnypersonal/rebootindia)

```
rebootindia/
├─ CLAUDE.md                    # this brief
├─ README.md
├─ .github/workflows/
│   ├─ new-problems.yml         # cron: every 3h  → national + city rotation
│   ├─ trend-scan.yml           # cron: hourly    → Trend Scout
│   ├─ follow-ups.yml           # cron: daily     → follow-up chase
│   └─ growth-review.yml        # cron: daily     → (Phase 2) engagement read-back
├─ src/
│   ├─ director.py              # orchestration: pick task(s), route, log
│   ├─ model_router.py          # multi-provider LLM fallback (§3a) — used by worker.py + reviewer.py
│   ├─ trend_scout.py           # Google Trends RSS + GDELT spike detection
│   ├─ news_gdelt.py            # GDELT query + parse + RSS fallback + image extraction
│   ├─ worker.py                # builds 4-persona prompt, calls Gemini, extracts JSON
│   ├─ prompt_worker.py         # the 4-persona master prompt template
│   ├─ reviewer.py              # Pass A (deterministic) + Pass B (Gemini verify call)
│   ├─ prompt_reviewer.py       # the verification prompt template
│   ├─ post_twitter.py          # X API v2 posting
│   ├─ post_facebook.py         # Graph API posting
│   ├─ post_instagram.py        # Instagram Graph API (container → publish)
│   ├─ growth.py                # (Phase 2) reads engagement, adjusts priority weights
│   ├─ store.py                 # SQLite state: queue, logs, trends, follow-ups
│   └─ config.py                # domains, cities, handles, caps, satire ratio, language map
├─ data/
│   ├─ state.db                 # SQLite (committed)
│   ├─ handles.yaml              # ministry/opposition/media handles
│   ├─ domains.yaml               # national domain list (priority=high, default)
│   └─ cities.yaml                # city/district rotation pool
└─ tests/
    └─ test_*.py
```

---

## 6. Reviewer / Verifier — Full Spec

**Pass A — deterministic, code only, ₹0, runs on every post:**
- Recount `twitter.charCount` independently — never trust the Worker's self-reported number
- Confirm required handles present: `@TheDeshBhakt` always; `@narendramodi` if `level=Central`;
  ministry handle present or explicitly empty (never a guess/placeholder)
- Confirm `sourceUrl` resolves with an HTTP 200 (HEAD request, short timeout, retry once)
- Force `instagram.ready=false` if `header.imageUrl` is empty — no exceptions, no stock photos
- Screen for banned/defamatory absolutes ("guilty", "criminal", "corrupt" stated as settled
  fact rather than alleged/under-scrutiny) against a maintained wordlist in `config.py`
- Hashtag count sanity (≤3 for Twitter, per §9 growth guidance)
- If `header.satire=true`: confirm `header.factAnchor` is present and non-empty (§8)

**Pass B — second Gemini Flash call, ₹0 but counted in volume budget, runs on every post:**
- Input: the source snippet + the generated post text (not the whole article, keep it small)
- Prompt: "Does this post assert any fact, number, quote, or event not supported by the
  source? Answer strictly as JSON: `{"supported": true|false, "issues": ["..."]}`"
- If `supported=false`: bounce to Worker with the issues appended as feedback, ONE retry only
- If still unsupported after retry: drop that platform's post, log the reason, do not post

**Never bypass Pass B to save quota.** If daily Gemini budget is tight, reduce post *volume*
(§7), not review coverage. An unreviewed post is a bigger risk to the mission than one fewer
post that day.

---

## 7. Validated Frequency Plan (replaces the literal "2x/day every city" ask)

**Why the literal version doesn't work:** 750+ districts × ~12 domains × 2/day is tens of
thousands of posts/day. No free tier survives that, and platforms rate-limit or suspend
accounts that post at bot-like frequency regardless of API tier. "Target as many as can"
is implemented here as *maximize within sustainable, free-tier-safe bounds*, not literal
saturation.

**The tiered plan:**

| Tier | Cadence | Volume/day (default) | Priority |
|---|---|---|---|
| National domains (~12: Education, Healthcare, Infra, Unemployment, Farmers, Corruption, Pollution, Women Safety, Economy, Judiciary, Energy, Digital India) | Guaranteed 2×/day each | ~24 | Highest — always scheduled |
| Trending (hourly scan, post only on genuine spike, deduped 24h) | Event-driven, capped | up to +10 | High when triggered |
| City/district rotation (priority pool of top ~50–100, not all 750+) | Rotates so most are covered within a week or two, not daily | fills remaining budget | Lower, fills gaps |
| **Total campaigns/day (default ceiling)** | | **~40** | Config-tunable in `config.py` |

Each campaign → up to 3 platform posts (TW/FB/IG) + up to 3 Gemini calls (1 Worker + up to 2
Reviewer). At 40 campaigns/day that's up to 120 Gemini calls/day — comfortably inside Gemini
Flash's free daily cap, with headroom. **X's actual free write cap (verify at T4b) is the
real ceiling** — if it's lower than 40/day, the config cap drops to match it, campaigns don't
silently overflow onto only 2 platforms.

Trend Scout runs hourly regardless of posting cadence — checking is free and cheap; posting
is what's rationed.

---

## 8. Satire Mode — Guardrails

Satire is allowed and can be effective for reach, with rules:

- Every satirical post must carry `header.satire=true` and `header.factAnchor` — the exact
  verified number/fact from the source that the satire is built on. No factAnchor, no post.
- Never fabricate a quote and attribute it to a real, named person — satirize the *situation*
  or the *gap between promise and reality*, not invented dialogue.
- Exaggeration and irony are fine; presenting a fabricated event as if it happened is not.
  The line: a reader who only reads the headline should not come away believing something
  false actually occurred.
- Default cap: satire ≤ ~20% of daily posts (tunable in `config.py`) — keeps the account's
  core credibility as an accountability source, which is what makes the serious posts land.

---

## 9. Growth & Engagement Strategy (digital-marketing-expert layer)

- **Timing:** schedule national posts inside IST peak windows (approx. 8–10am, 1–2pm,
  7–10pm) rather than mechanically every N hours — Director's scheduler should weight these
  windows, not just fire on a flat interval.
- **Hashtags:** 1 trending tag (from Trend Scout) + 1–2 evergreen tags (`#RebootIndia
  #AccountabilityNow` style) — cap 3 total. More reads as spam, not virality.
- **Cross-platform funnel:** Instagram caption references "full story on X"; Twitter can
  thread into the Facebook long-form for readers who want depth.
- **Variety:** rotate tone (serious / satire / inspirational per the original 3-tone vision)
  so the feed doesn't read as monotone outrage.
- **(Phase 2) Engagement feedback loop:** `growth.py` reads back likes/shares/comments via
  the same free Graph/X read endpoints and nudges future domain/city selection toward what
  resonates — this needs the free-tier *read* metrics availability confirmed too; don't
  assume it's unlimited just because posting is free.

---

## 10. Guardrails (full list)

- HIGH PRECISION fact-check in the Worker; independent re-verification in the Reviewer.
- No defamation: state facts, attribute to source, frame as accountability questions on
  unresolved matters rather than settled verdicts.
- Satire stays fact-anchored (§8) — never a vector for actual misinformation.
- Respect free-tier caps on every layer (Gemini, X, IG, GitHub Actions minutes); throttle
  volume before ever considering a paid upgrade, and only upgrade with CEO sign-off.
- No scraping behind logins; GDELT + public RSS + official Graph/X/Trends APIs only.
- Idempotent posting: a task marked `processing` is never double-posted, including across
  the 3h/hourly/daily schedules overlapping.

---

## 11. Build Backlog v2 (execute in order)

- [x] **T1** Scaffold repo (confirm public visibility for free Actions minutes); `requirements.txt`, `.gitignore`, README.
      *(built; repo visibility itself is still a CEO decision, §12 #1)*
- [x] **T2** `config.py` + `domains.yaml` (12 national domains, priority=high) + `cities.yaml`
      (seed ~50–100 priority districts) + `handles.yaml`.
- [x] **T3** `store.py` — SQLite schema (tasks, logs, trends) + init + seed loader.
- [x] **T4** `news_gdelt.py` — GDELT query + image extraction (`socialimage` + og:image
      fallback) + RSS fallback.
- [ ] **T4b** Probe X API's actual current free-tier write cap; write the number into
      `config.py` as the binding daily ceiling; report it back before going live.
      *(tooling built — `src/probe_x_limits.py`, posts+immediately-deletes one throwaway
      tweet and reads back the rate-limit headers, gated behind an explicit `--yes` flag
      since it's a real (if brief) write to the account. Not yet run — no X credentials
      available in the build environment. `DAILY_CAMPAIGN_CAP` still defaults to 40,
      unverified against X's real cap; a human with live creds needs to run it, per README.)*
- [x] **T5** `trend_scout.py` — Google Trends India RSS + GDELT volume-spike scorer; inserts
      deduped HIGH-priority tasks. *(Trends RSS URL above had moved to `/trending/rss` —
      fixed and verified live during the build; the old `/trends/trendingsearches/daily/rss`
      path 404s.)*
- [x] **T5b** `model_router.py` — OpenAI-compatible adapter for Gemini/Groq/Cerebras/Mistral;
      priority-ordered failover; logs which provider served each call.
- [x] **T6** `prompt_worker.py` + `worker.py` — 4-persona call **via model_router**, marker
      extraction, schema validation, satire/factAnchor enforcement.
- [x] **T7** `prompt_reviewer.py` + `reviewer.py` — Pass A (deterministic) + Pass B (second
      call **via model_router**) + retry-once logic.
- [x] **T8** `post_twitter.py` + `post_facebook.py` + `post_instagram.py` — graceful
      per-platform skip on `ready=false`.
- [x] **T9** `director.py` — full flow wired: Trend Scout → News → Worker → Reviewer →
      Poster → Logger; `--dry-run` mode (generate + review, never post).
- [x] **T10** Follow-up flow: re-fetches fresh news per due followup and re-runs the pipeline
      with the original post attached as context, so the Worker writes a status update
      (resolved/partial/unchanged/worsened) rather than repeating the original report.
- [x] **T11** GitHub Actions workflows (4 crons per §5) + Secrets wiring; commit `state.db`.
      *(plus a 5th, `tests.yml`, running the unit suite on every PR/push to `main`.)*
- [x] **T12** Tests: director selection, extraction, char-limit, idempotency, Reviewer bounce/retry.
      *(42 tests, `python -m unittest discover -s tests`.)*
- [x] **T13** `growth.py` — reads back likes/shares/comments per posted campaign, scores
      domain/city average engagement, and persists clamped weight multipliers
      (`GROWTH_WEIGHT_MIN`–`GROWTH_WEIGHT_MAX`) that `director.py` uses to reorder national
      domains and bias city-rotation frequency — a nudge only, never a gate: national cadence
      stays guaranteed and every city still cycles through rotation regardless of weight.
      Groups under `GROWTH_MIN_SAMPLE_SIZE` posted campaigns stay unweighted rather than
      being scored on noise. Read-endpoint availability on free tiers is still unconfirmed
      (§9) — every fetch degrades to "no signal" on failure instead of raising.
- [x] **T14** Website hook: `publish_website.py` POSTs each Reviewer-approved campaign to
      `WEBSITE_PUBLISH_URL`. The exact CMS rebootindia.com runs on wasn't specified when this
      was built, so it targets a generic, documented JSON contract (see the module docstring
      and README) rather than a specific platform's API shape — untested against a real
      endpoint until the site's actual backend is confirmed.

Always dry-run until CEO explicitly approves live posting. Dry-run needs no live posting
keys — only read/verification calls if we choose to test those early.

---

## 12. Decisions Pending (CEO to confirm)

1. Public repo confirmed? (needed for free unlimited Actions minutes) — repo is currently
   empty/new; confirm visibility (public/private) before T1.
2. Daily campaign ceiling: default 40, pending T4b's real X cap — confirm or override.
3. Satire ratio cap: default 20% — confirm or override.
4. Priority city/district pool (~50–100): who picks the list, or should Claude Code seed it
   from population/news-volume data?
5. State store: SQLite in repo (default) vs Google Sheets for a visual dashboard.
6. Model Router provider order: default Gemini → Groq → Cerebras → Mistral (§3a) — confirm,
   and get free-tier API keys for all four before T5b (Gemini and Groq need no card; Cerebras
   and Mistral, confirm at signup time).

Do not go live until 1–5 are settled and the Instagram/Facebook/X one-time human account
setup (v1 doc §4) is complete — that step needs the CEO personally, Claude Code cannot click
through Meta's or X's consent screens.

---

*This file is the source of truth for the build. Update it in the repo as decisions land —
don't let it drift from what's actually running.*

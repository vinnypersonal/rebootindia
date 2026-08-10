"""Central config: caps, provider order, banned phrases, file paths.

Every knob the CEO can tune (§12 Decisions Pending) lives here with the default
CLAUDE.md v2 specifies. Nothing here talks to the network.
"""
import os
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "state.db"

# --- §7 Volume plan ---------------------------------------------------------
DAILY_CAMPAIGN_CAP = int(os.environ.get("REBOOT_DAILY_CAMPAIGN_CAP", 40))  # Decision #2, pending T4b
NATIONAL_DOMAIN_CADENCE_PER_DAY = 2
TREND_CAMPAIGN_CAP_PER_DAY = 10

# --- §8 Satire guardrails ---------------------------------------------------
SATIRE_MAX_RATIO = float(os.environ.get("REBOOT_SATIRE_RATIO", 0.20))  # Decision #3

# --- §9 Growth / hashtags ---------------------------------------------------
MAX_HASHTAGS = 3
IST_PEAK_WINDOWS = [(8, 10), (13, 14), (19, 22)]  # (start_hour, end_hour), IST, 24h clock

# --- Platform limits ---------------------------------------------------------
TWITTER_CHAR_LIMIT = 280

# --- §6 Reviewer Pass A: banned/defamatory absolutes ------------------------
# Words asserting settled guilt as fact rather than alleged/under-scrutiny.
# Maintain this list deliberately; Reviewer bounces any post containing one of
# these applied directly to a named person/entity outside a quote.
BANNED_ABSOLUTE_PHRASES = [
    "is guilty",
    "is a criminal",
    "is corrupt",
    "stole",
    "is a thief",
    "committed fraud",
    "is a fraud",
]

# --- §3a Model Router --------------------------------------------------------
# Priority order + OpenAI-compatible endpoint config. API keys come from env
# (GitHub Actions Secrets in prod). Verify free-tier limits at build time —
# they move without notice; this table is descriptive, not enforced in code.
MODEL_PROVIDERS = [
    {
        "name": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": "gemini-2.5-flash",
        "api_key_env": "GEMINI_API_KEY",
    },
    {
        "name": "groq",
        "base_url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "api_key_env": "GROQ_API_KEY",
    },
    {
        "name": "cerebras",
        "base_url": "https://api.cerebras.ai/v1/chat/completions",
        "model": "llama-3.3-70b",
        "api_key_env": "CEREBRAS_API_KEY",
    },
    {
        "name": "mistral",
        "base_url": "https://api.mistral.ai/v1/chat/completions",
        "model": "mistral-small-latest",
        "api_key_env": "MISTRAL_API_KEY",
    },
]

_domains_cache = None
_cities_cache = None
_handles_cache = None


def load_domains():
    global _domains_cache
    if _domains_cache is None:
        with open(DATA_DIR / "domains.yaml") as f:
            _domains_cache = yaml.safe_load(f)["domains"]
    return _domains_cache


def load_cities():
    global _cities_cache
    if _cities_cache is None:
        with open(DATA_DIR / "cities.yaml") as f:
            _cities_cache = yaml.safe_load(f)["cities"]
    return _cities_cache


def load_handles():
    global _handles_cache
    if _handles_cache is None:
        with open(DATA_DIR / "handles.yaml") as f:
            _handles_cache = yaml.safe_load(f)
    return _handles_cache

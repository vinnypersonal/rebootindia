"""Model Router (CLAUDE.md §3a): one function, many free-tier LLM providers.

Tries providers in priority order (config.MODEL_PROVIDERS), fails over on
429/error/timeout. All four candidates expose an OpenAI-compatible
chat-completions endpoint, so one adapter shape covers all of them.

Never falls back to a paid call. If every provider is exhausted, raises
AllProvidersExhausted — the caller (worker/reviewer) must skip that campaign
and log it, not retry into a paid tier.
"""
import os

import requests

from . import config

DEFAULT_TIMEOUT = 30


class AllProvidersExhausted(Exception):
    pass


def _call_provider(provider, messages, temperature, max_tokens, timeout):
    api_key = os.environ.get(provider["api_key_env"])
    if not api_key:
        raise RuntimeError(f"{provider['name']}: no API key set ({provider['api_key_env']})")

    resp = requests.post(
        provider["base_url"],
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": provider["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=timeout,
    )
    if resp.status_code == 429:
        raise RuntimeError(f"{provider['name']}: rate limited (429)")
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def call_llm(messages, temperature=0.4, max_tokens=1500, timeout=DEFAULT_TIMEOUT,
             conn=None, task_id=None, stage="worker"):
    """Try each provider in config.MODEL_PROVIDERS priority order.

    Returns (text, provider_name). Logs the failover chain to `logs.llm_provider`
    via store.log if a db connection is supplied.
    """
    from . import store  # local import: avoid a hard circular dep at module load

    errors = []
    for provider in config.MODEL_PROVIDERS:
        try:
            text = _call_provider(provider, messages, temperature, max_tokens, timeout)
            if conn is not None:
                store.log(conn, task_id, stage,
                           f"served by {provider['name']}", llm_provider=provider["name"])
            return text, provider["name"]
        except Exception as exc:  # noqa: BLE001 - deliberately broad, we failover on anything
            errors.append(f"{provider['name']}: {exc}")
            if conn is not None:
                store.log(conn, task_id, stage,
                           f"failover from {provider['name']}: {exc}", level="warn",
                           llm_provider=provider["name"])
            continue

    raise AllProvidersExhausted(
        "All model providers exhausted:\n" + "\n".join(errors)
    )

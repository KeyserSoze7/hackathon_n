"""Claude-written prose (defect notices, RTI drafts, citizen replies). Callers always have a template fallback.

Claude never computes numbers: callers pass precomputed facts and Claude only rewrites them as prose.
write() returns None when Claude is slow (> CLAUDE_TIMEOUT_S), fails, refuses, or no credentials are
configured, so the endpoint serves its template instead of an error.
Credentials: ANTHROPIC_API_KEY in the environment or the repo-root .env (loaded by backend.database).
"""
import logging
import os

import anthropic

import backend.database  # noqa: F401  (loads the repo-root .env)

MODEL = "claude-opus-5-5"
TIMEOUT_S = float(os.environ.get("CLAUDE_TIMEOUT_S", "25"))
log = logging.getLogger("claude_writer")
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(timeout=TIMEOUT_S, max_retries=0)  # one attempt: the template is the retry
    return _client


def write(system: str, prompt: str, max_tokens: int = 4000):
    """One Claude call at low effort. Returns the text, or None (caller falls back to its template)."""
    try:
        response = _get_client().beta.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # on a policy decline the API re-runs the request on a fallback model
        )
    except anthropic.APITimeoutError:
        log.warning("Claude timed out after %ss; using template", TIMEOUT_S)
        return None
    except anthropic.RateLimitError:
        log.warning("Claude rate limited; using template")
        return None
    except anthropic.APIStatusError as e:
        log.warning("Claude API error %s; using template", e.status_code)
        return None
    except anthropic.APIConnectionError:
        log.warning("Claude unreachable; using template")
        return None
    except Exception as e:  # e.g. no credentials configured: never fail the endpoint over prose
        log.warning("Claude unavailable (%s); using template", type(e).__name__)
        return None
    if response.stop_reason in ("refusal", "max_tokens"):
        log.warning("Claude stop_reason=%s; using template", response.stop_reason)
        return None
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text or None

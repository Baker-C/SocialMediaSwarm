"""LLM steps for hourly content (prompt files + Claude)."""

from __future__ import annotations

import logging

from app.hourly_crew import prompt_loader
from app.hourly_crew.context_extract import extract_context_hints
from app.infrastructure.claude_client import get_claude_client

logger = logging.getLogger(__name__)

_MIN_POST_LEN = 50
_MAX_POST_LEN = 280


def _account_prompt_section(account_system_prompt: str) -> str:
    prompt = (account_system_prompt or "").strip()
    if not prompt:
        return ""
    return f"Account instructions:\n{prompt}\n\n"


def generate_candidates(
    niche: str,
    prompt_bundle: str,
    n: int,
    *,
    account_system_prompt: str = "",
) -> list[str]:
    niche_s = niche.strip() or "general"
    bundle = (prompt_bundle or "").strip()
    claude = get_claude_client()
    if claude.enabled:
        try:
            system = prompt_loader.load_template(
                "tasks/generate_candidates.system.md",
                n=n,
            )
            user = prompt_loader.load_template(
                "tasks/generate_candidates.user.md",
                niche=niche_s,
                account_system_prompt_section=_account_prompt_section(account_system_prompt),
                context=bundle[:10000],
            )
            data = claude.messages_json_dict(system=system, user=user, max_tokens=4096)
            posts = (data or {}).get("posts")
            if isinstance(posts, list):
                cleaned: list[str] = []
                for p in posts:
                    if isinstance(p, str):
                        t = p.strip()
                        if 10 <= len(t) <= 300:
                            cleaned.append(t[:280])
                    if len(cleaned) >= n:
                        break
                if len(cleaned) >= min(1, n):
                    return cleaned[:n]
                logger.warning(
                    "generate_candidates: Claude returned no valid posts (parsed=%s)",
                    type(posts).__name__,
                )
        except Exception as exc:
            logger.warning("generate_candidates LLM failed: %s", exc)
    else:
        logger.warning("generate_candidates: ANTHROPIC_API_KEY not set; using structured fallback")
    return _fallback_candidates(niche_s, bundle, n)


def rank_candidates(candidates: list[str], prompt_bundle: str) -> list[str]:
    if len(candidates) <= 1:
        return list(candidates)
    claude = get_claude_client()
    if claude.enabled:
        try:
            numbered = "\n".join(f"{i}. {text}" for i, text in enumerate(candidates))
            system = prompt_loader.load("tasks/rank_candidates.system.md")
            user = prompt_loader.load_template(
                "tasks/rank_candidates.user.md",
                context=prompt_bundle[:8000],
                candidates=numbered,
            )
            data = claude.messages_json_dict(system=system, user=user, max_tokens=1024)
            order = (data or {}).get("order")
            if isinstance(order, list):
                idxs: list[int] = []
                for x in order:
                    if isinstance(x, int) and 0 <= x < len(candidates) and x not in idxs:
                        idxs.append(x)
                for i in range(len(candidates)):
                    if i not in idxs:
                        idxs.append(i)
                return [candidates[i] for i in idxs]
        except Exception as exc:
            logger.warning("rank_candidates LLM failed: %s", exc)
    return list(candidates)


def _pad_post_body(body: str) -> str:
    text = " ".join(body.split())
    if len(text) < _MIN_POST_LEN:
        text = (text + " More context and follow-up soon.").strip()
    if len(text) < _MIN_POST_LEN:
        text = text.ljust(_MIN_POST_LEN, ".")
    return text[:_MAX_POST_LEN]


def _fallback_candidates(niche: str, bundle: str, n: int) -> list[str]:
    """Deterministic posts from parsed tick context — never embed raw prompt JSON."""
    hints = extract_context_hints(bundle, niche)
    topic = hints.get("topic") or niche
    discourse = hints.get("discourse", "")
    trends = hints.get("trends", "")
    sample = hints.get("sample_post", "")

    templates: list[str] = []
    if sample:
        templates.append(
            f"Wait—{topic} again? "
            f"The cycle is exhausting, but the underlying move still matters for anyone tracking {niche}."
        )
    if trends:
        templates.append(
            f"Seriously—{trends} and {topic} in the same week? "
            f"Feels chaotic, but that overlap is exactly what {niche} watchers should notice."
        )
    if discourse:
        templates.append(
            f"Nobody's saying this plainly: {discourse[:120]} "
            f"That's the part people following {niche} will feel in their feeds."
        )
    templates.extend(
        [
            f"Wild how {topic} keeps getting handled by executive orders and lawsuits—not votes. "
            f"Same dysfunction, new headline. If you care about {niche}, that's the story.",
            f"Am I the only one tired of {topic} being 'fixed' in court instead of Congress? "
            f"For {niche} readers, the pattern is the point.",
            f"This is not normal: {topic} drifts from debate to decree overnight. "
            f"Worth watching if {niche} is your beat.",
        ]
    )

    out: list[str] = []
    seen: set[str] = set()
    for i in range(max(1, n)):
        raw = templates[i % len(templates)]
        body = _pad_post_body(raw)
        if body in seen:
            body = _pad_post_body(f"{raw} (variant {i + 1})")
        seen.add(body)
        out.append(body)
    return out[:n]

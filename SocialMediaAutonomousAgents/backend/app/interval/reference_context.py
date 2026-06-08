"""Format pipeline reference-analysis briefs for the compose prompt."""

from __future__ import annotations

from typing import Any


def _brief_section(title: str, analysis: dict[str, Any] | None, *, skipped_note: str) -> list[str]:
    if not analysis:
        return []
    if analysis.get("skipped"):
        return [f"({skipped_note})"]
    lines = [title]
    summary = str(analysis.get("pattern_summary") or "").strip()
    if summary:
        lines.append(f"Summary: {summary}")
    topics = analysis.get("winning_topics")
    if isinstance(topics, list) and topics:
        shown = ", ".join(str(t) for t in topics[:8])
        lines.append(f"Winning topics: {shown}")
    signals = analysis.get("voice_signals")
    if isinstance(signals, list) and signals:
        lines.append("Voice signals:")
        lines.extend(f"- {s}" for s in signals[:6] if str(s).strip())
    constraints = analysis.get("recommended_constraints")
    if isinstance(constraints, list) and constraints:
        lines.append("Emulate or avoid:")
        lines.extend(f"- {c}" for c in constraints[:6] if str(c).strip())
    entities = analysis.get("features", {}).get("entity_tags") if isinstance(analysis.get("features"), dict) else None
    if isinstance(entities, list) and entities:
        lines.append(f"Entity tags: {', '.join(str(e) for e in entities[:8])}")
    return lines


def format_reference_context_for_compose(
    timeline_analysis: dict[str, Any] | None,
    own_posts_analysis: dict[str, Any] | None,
) -> str:
    """Human-readable block injected into compose (topic from winner; voice from briefs)."""
    parts: list[str] = []
    parts.extend(
        _brief_section(
            "### External timeline patterns (topic + what's viral now)",
            timeline_analysis,
            skipped_note="External timeline pattern analysis was skipped this tick.",
        )
    )
    own_lines = _brief_section(
        "### Your account's top-performing posts (voice + structure)",
        own_posts_analysis,
        skipped_note="Own-post analysis skipped — not enough tracked post history yet.",
    )
    if own_lines:
        if parts:
            parts.append("")
        parts.extend(own_lines)
    if not parts:
        return "(No reference analysis available for this tick.)"
    parts.append(
        "\nUse the source tweet below for topic and link. "
        "Let the briefs nudge tone and structure — do not copy wording from references."
    )
    return "\n".join(parts).strip()

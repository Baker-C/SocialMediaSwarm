"""Voice version initialization and bump behavior."""

from unittest.mock import MagicMock

from app.models.account import AccountDocument
from app.services.voice_version_service import bump_voice_version_if_needed, compute_voice_hash


def _account(**kwargs: object) -> AccountDocument:
    base = {"account_id": "acct1", "niche": "news"}
    base.update(kwargs)
    return AccountDocument.model_validate(base)


def test_first_init_sets_v1_and_writes_revision() -> None:
    acc = _account()
    acc.system_prompt = "Write hot takes."
    acc.personality = "Snappy left-leaning voice."
    repo = MagicMock()

    out = bump_voice_version_if_needed(acc, previous_hash=None, revision_repo=repo)

    assert out.voice_version_seq == 1
    assert out.voice_version_label == "v1"
    assert out.voice_version_hash == compute_voice_hash(
        system_prompt=out.system_prompt,
        personality=out.personality,
    )
    repo.save.assert_called_once()
    saved = repo.save.call_args[0][0]
    assert saved.seq == 1
    assert saved.label == "v1"


def test_unchanged_voice_skips_revision_write() -> None:
    acc = _account()
    acc.system_prompt = "Same prompt"
    acc.personality = "Same personality"
    h = compute_voice_hash(system_prompt=acc.system_prompt, personality=acc.personality)
    acc.voice_version_hash = h
    acc.voice_version_seq = 1
    acc.voice_version_label = "v1"
    repo = MagicMock()

    out = bump_voice_version_if_needed(acc, previous_hash=h, revision_repo=repo)

    assert out.voice_version_seq == 1
    repo.save.assert_not_called()


def test_voice_change_bumps_to_v2() -> None:
    acc = _account()
    acc.system_prompt = "New prompt"
    acc.personality = "Old personality"
    old_hash = compute_voice_hash(system_prompt="Old prompt", personality="Old personality")
    acc.voice_version_hash = old_hash
    acc.voice_version_seq = 1
    acc.voice_version_label = "v1"
    repo = MagicMock()

    out = bump_voice_version_if_needed(acc, previous_hash=old_hash, revision_repo=repo)

    assert out.voice_version_seq == 2
    assert out.voice_version_label == "v2"
    repo.save.assert_called_once()
    assert repo.save.call_args[0][0].seq == 2

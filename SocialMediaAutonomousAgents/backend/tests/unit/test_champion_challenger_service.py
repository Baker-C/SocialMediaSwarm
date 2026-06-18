"""Tests for champion/challenger scoring and decision rules."""

import pytest

from app.models.outcome_ledger import OutcomeLedgerDocument
from app.services.champion_challenger_service import (
    PromotionVerdict,
    RegressionVerdict,
    SpecScore,
    evaluate_promotion,
    evaluate_regression,
    score_pipeline_hash,
    score_soul_hash,
)
from app.services.outcome_ledger_repository import OutcomeLedgerRepository


class FakeOutcomeLedgerRepository(OutcomeLedgerRepository):
    """Stub repository for testing; stores rows in memory."""

    def __init__(self):
        super().__init__()
        self._rows: dict[str, list[OutcomeLedgerDocument]] = {}

    def add_row(self, account_id: str, pipeline_hash: str, soul_hash: str, reward: float | None) -> None:
        """Add a ledger row for testing."""
        doc = OutcomeLedgerDocument(
            account_id=account_id,
            post_id=f"post_{len(self._rows)}",
            run_id=None,
            soul_hash=soul_hash,
            pipeline_hash=pipeline_hash,
            reward=reward,
            recorded_at="2026-06-18T12:00:00Z",
        )
        key = (account_id, pipeline_hash, soul_hash)
        if key not in self._rows:
            self._rows[key] = []
        self._rows[key].append(doc)

    def list_for_pipeline_hash(
        self, pipeline_hash: str, *, account_id: str | None = None, limit: int = 500
    ) -> list[OutcomeLedgerDocument]:
        """Return rows matching the pipeline hash."""
        out = []
        for (aid, ph, _), rows in self._rows.items():
            if ph == pipeline_hash and (account_id is None or aid == account_id):
                out.extend(rows)
        return out[:limit]

    def list_for_soul_hash(
        self, soul_hash: str, *, account_id: str | None = None, limit: int = 500
    ) -> list[OutcomeLedgerDocument]:
        """Return rows matching the soul hash."""
        out = []
        for (aid, _, sh), rows in self._rows.items():
            if sh == soul_hash and (account_id is None or aid == account_id):
                out.extend(rows)
        return out[:limit]


class TestScorePipelineHash:
    """Tests for score_pipeline_hash aggregation."""

    def test_score_with_mixed_rewards(self):
        """None rewards are excluded; only non-None are averaged."""
        ledger = FakeOutcomeLedgerRepository()
        aid = "test_account"
        ph = "pipeline_v1"

        ledger.add_row(aid, ph, "soul_v1", 0.5)
        ledger.add_row(aid, ph, "soul_v1", 0.7)
        ledger.add_row(aid, ph, "soul_v1", None)  # unpolled, excluded
        ledger.add_row(aid, ph, "soul_v1", 0.6)

        score = score_pipeline_hash(ph, account_id=aid, ledger=ledger)

        assert score.pipeline_hash == ph
        assert score.n_scored == 3
        assert score.n_total == 4
        assert score.avg_reward == pytest.approx((0.5 + 0.7 + 0.6) / 3)

    def test_score_all_none_rewards(self):
        """When all rewards are None, avg_reward is None and n_scored is 0."""
        ledger = FakeOutcomeLedgerRepository()
        aid = "test_account"
        ph = "pipeline_v1"

        ledger.add_row(aid, ph, "soul_v1", None)
        ledger.add_row(aid, ph, "soul_v1", None)

        score = score_pipeline_hash(ph, account_id=aid, ledger=ledger)

        assert score.n_scored == 0
        assert score.n_total == 2
        assert score.avg_reward is None

    def test_score_no_rows(self):
        """Empty ledger returns zero counts and None average."""
        ledger = FakeOutcomeLedgerRepository()
        score = score_pipeline_hash("nonexistent", account_id="test_account", ledger=ledger)

        assert score.n_scored == 0
        assert score.n_total == 0
        assert score.avg_reward is None


class TestScoreSoulHash:
    """Tests for score_soul_hash aggregation (mirrors pipeline hash)."""

    def test_score_soul_with_mixed_rewards(self):
        """Soul hashes scored independently from pipeline hashes."""
        ledger = FakeOutcomeLedgerRepository()
        aid = "test_account"
        sh = "soul_v2"

        ledger.add_row(aid, "pipeline_v1", sh, 0.4)
        ledger.add_row(aid, "pipeline_v2", sh, 0.5)
        ledger.add_row(aid, "pipeline_v1", sh, None)
        ledger.add_row(aid, "pipeline_v2", sh, 0.6)

        score = score_soul_hash(sh, account_id=aid, ledger=ledger)

        assert score.pipeline_hash == sh  # reuses dataclass, stores soul hash here
        assert score.n_scored == 3
        assert score.n_total == 4
        assert score.avg_reward == pytest.approx((0.4 + 0.5 + 0.6) / 3)


class TestEvaluatePromotion:
    """Tests for promotion eligibility rule."""

    def test_promotion_eligible_improved(self):
        """Challenger with enough data and sufficient delta → eligible."""
        ledger = FakeOutcomeLedgerRepository()
        aid = "test_account"
        champ_ph = "pipeline_v1"
        chal_ph = "pipeline_v2"

        # Champion: 10 scored posts, avg reward 0.5
        for i in range(10):
            ledger.add_row(aid, champ_ph, "soul_v1", 0.5)

        # Challenger: 10 scored posts, avg reward 0.53 (delta = 0.03 > min 0.02)
        for i in range(10):
            ledger.add_row(aid, chal_ph, "soul_v1", 0.53)

        verdict = evaluate_promotion(
            aid,
            champion_hash=champ_ph,
            challenger_hash=chal_ph,
            min_window=10,
            min_improvement=0.02,
            ledger=ledger,
        )

        assert verdict.eligible is True
        assert verdict.reason == "improved"
        assert verdict.delta == pytest.approx(0.03)
        assert verdict.champion.avg_reward == pytest.approx(0.5)
        assert verdict.challenger.avg_reward == pytest.approx(0.53)

    def test_promotion_insufficient_window(self):
        """Champion below min_window → insufficient_window."""
        ledger = FakeOutcomeLedgerRepository()
        aid = "test_account"
        champ_ph = "pipeline_v1"
        chal_ph = "pipeline_v2"

        # Champion: only 5 scored posts (below min 10)
        for i in range(5):
            ledger.add_row(aid, champ_ph, "soul_v1", 0.5)

        # Challenger: 10 scored posts, much better (0.6)
        for i in range(10):
            ledger.add_row(aid, chal_ph, "soul_v1", 0.6)

        verdict = evaluate_promotion(
            aid,
            champion_hash=champ_ph,
            challenger_hash=chal_ph,
            min_window=10,
            min_improvement=0.02,
            ledger=ledger,
        )

        assert verdict.eligible is False
        assert verdict.reason == "insufficient_window"
        assert verdict.delta is None

    def test_promotion_no_improvement(self):
        """Challenger delta below min_improvement → not eligible."""
        ledger = FakeOutcomeLedgerRepository()
        aid = "test_account"
        champ_ph = "pipeline_v1"
        chal_ph = "pipeline_v2"

        # Champion: 10 posts, avg 0.5
        for i in range(10):
            ledger.add_row(aid, champ_ph, "soul_v1", 0.5)

        # Challenger: 10 posts, avg 0.51 (delta = 0.01 < min 0.02)
        for i in range(10):
            ledger.add_row(aid, chal_ph, "soul_v1", 0.51)

        verdict = evaluate_promotion(
            aid,
            champion_hash=champ_ph,
            challenger_hash=chal_ph,
            min_window=10,
            min_improvement=0.02,
            ledger=ledger,
        )

        assert verdict.eligible is False
        assert verdict.reason == "no_improvement"
        assert verdict.delta == pytest.approx(0.01)


class TestEvaluateRegression:
    """Tests for hard-regression detection."""

    def test_regression_hard_regression_detected(self):
        """Current champion out-scored by parent by >= hard_drop → regressed."""
        ledger = FakeOutcomeLedgerRepository()
        aid = "test_account"
        current_ph = "pipeline_v4"
        parent_ph = "pipeline_v3"

        # Parent: 10 posts, avg 0.6
        for i in range(10):
            ledger.add_row(aid, parent_ph, "soul_v1", 0.6)

        # Current: 10 posts, avg 0.54 (drop = 0.06 > hard_drop 0.05)
        for i in range(10):
            ledger.add_row(aid, current_ph, "soul_v1", 0.54)

        verdict = evaluate_regression(
            aid,
            current_hash=current_ph,
            parent_hash=parent_ph,
            min_window=10,
            hard_drop=0.05,
            ledger=ledger,
        )

        assert verdict.regressed is True
        assert verdict.reason == "hard_regression"
        assert verdict.drop == pytest.approx(0.06)

    def test_regression_no_parent(self):
        """No parent hash → no_parent."""
        ledger = FakeOutcomeLedgerRepository()
        aid = "test_account"
        current_ph = "pipeline_v1"

        ledger.add_row(aid, current_ph, "soul_v1", 0.5)

        verdict = evaluate_regression(
            aid,
            current_hash=current_ph,
            parent_hash=None,
            min_window=10,
            hard_drop=0.05,
            ledger=ledger,
        )

        assert verdict.regressed is False
        assert verdict.reason == "no_parent"
        assert verdict.parent is None

    def test_regression_insufficient_window(self):
        """Both under min_window → insufficient_window."""
        ledger = FakeOutcomeLedgerRepository()
        aid = "test_account"
        current_ph = "pipeline_v4"
        parent_ph = "pipeline_v3"

        # Parent: 5 scored posts (below min 10)
        for i in range(5):
            ledger.add_row(aid, parent_ph, "soul_v1", 0.6)

        # Current: 5 scored posts
        for i in range(5):
            ledger.add_row(aid, current_ph, "soul_v1", 0.54)

        verdict = evaluate_regression(
            aid,
            current_hash=current_ph,
            parent_hash=parent_ph,
            min_window=10,
            hard_drop=0.05,
            ledger=ledger,
        )

        assert verdict.regressed is False
        assert verdict.reason == "insufficient_window"

    def test_regression_stable(self):
        """Small drop below hard_drop threshold → stable."""
        ledger = FakeOutcomeLedgerRepository()
        aid = "test_account"
        current_ph = "pipeline_v4"
        parent_ph = "pipeline_v3"

        # Parent: 10 posts, avg 0.60
        for i in range(10):
            ledger.add_row(aid, parent_ph, "soul_v1", 0.60)

        # Current: 10 posts, avg 0.56 (drop = 0.04 < hard_drop 0.05)
        for i in range(10):
            ledger.add_row(aid, current_ph, "soul_v1", 0.56)

        verdict = evaluate_regression(
            aid,
            current_hash=current_ph,
            parent_hash=parent_ph,
            min_window=10,
            hard_drop=0.05,
            ledger=ledger,
        )

        assert verdict.regressed is False
        assert verdict.reason == "stable"
        assert verdict.drop == pytest.approx(0.04)

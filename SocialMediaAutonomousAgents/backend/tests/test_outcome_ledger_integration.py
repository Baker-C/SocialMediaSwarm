"""Integration tests for outcome ledger with PostCreationMetrics."""

from __future__ import annotations

import pytest
from app.models.tracked_post import PostCreationMetrics, TrackedPostDocument
from app.models.outcome_ledger import OutcomeLedgerDocument, compute_reward


class TestPostCreationMetricsWithOutcomeLedger:
    """Integration: PostCreationMetrics fields flow to OutcomeLedgerDocument."""

    def test_creation_metrics_fields_stamp_to_ledger(self) -> None:
        """Simulate the publish flow: creation_metrics → ledger stamp."""
        # 1. Create PostCreationMetrics with new fields (as runner.py does)
        creation_metrics = PostCreationMetrics(
            candidates_created=1,
            tweets_pulled=10,
            voice_version_hash="soul_abc",
            voice_version_seq=1,
            run_id="run_12345",  # NEW
            pipeline_hash="pipe_xyz",  # NEW
        )

        # 2. Simulate ledger.stamp() call (from post_tick.py)
        ledger_doc = OutcomeLedgerDocument(
            account_id="JohnJames_News",
            post_id="1234567890",
            run_id=creation_metrics.run_id,
            soul_hash=creation_metrics.voice_version_hash,
            pipeline_hash=creation_metrics.pipeline_hash,
        )

        # 3. Verify attribution fields match
        assert ledger_doc.run_id == "run_12345"
        assert ledger_doc.pipeline_hash == "pipe_xyz"
        assert ledger_doc.soul_hash == "soul_abc"

    def test_creation_metrics_without_new_fields_stamps_as_none(self) -> None:
        """Legacy posts (before attribution) stamp None values."""
        # Old creation_metrics (before doc 02)
        creation_metrics = PostCreationMetrics(
            candidates_created=1,
            voice_version_hash="soul_old",
            # No run_id, no pipeline_hash
        )

        ledger_doc = OutcomeLedgerDocument(
            account_id="test",
            post_id="123",
            run_id=creation_metrics.run_id,  # None
            soul_hash=creation_metrics.voice_version_hash,
            pipeline_hash=creation_metrics.pipeline_hash,  # None
        )

        assert ledger_doc.run_id is None
        assert ledger_doc.pipeline_hash is None
        assert ledger_doc.soul_hash == "soul_old"

    def test_tracked_post_contains_creation_metrics_with_attribution(self) -> None:
        """TrackedPostDocument.creation_metrics carries run_id + pipeline_hash."""
        metrics = PostCreationMetrics(
            candidates_created=1,
            run_id="run_abc",
            pipeline_hash="pipe_1",
            voice_version_hash="soul_v1",
        )

        post = TrackedPostDocument(
            account_id="test",
            tweet_id="123",
            creation_metrics=metrics,
        )

        # Verify we can read attribution from the post's creation_metrics
        assert post.creation_metrics.run_id == "run_abc"
        assert post.creation_metrics.pipeline_hash == "pipe_1"

    def test_ledger_reward_computed_from_metrics(self) -> None:
        """Ledger.reward flows from engagement_rate in metrics."""
        metrics = {
            "impression_count": 1000,
            "engagement_rate": 0.05,
        }

        reward = compute_reward(metrics)
        assert reward == 0.05

        # Simulate update_outcome call
        ledger_doc = OutcomeLedgerDocument(
            account_id="test",
            post_id="123",
            run_id="run_1",
            raw_metrics=metrics,
            reward=reward,  # Would be set by update_outcome
        )

        assert ledger_doc.reward == 0.05
        assert ledger_doc.raw_metrics["engagement_rate"] == 0.05

    def test_ledger_document_id_format_matches_tracked_post(self) -> None:
        """Ledger and TrackedPost use compatible document_id formats."""
        account_id = "JohnJames_News"
        post_id = "1234567890"

        ledger_id = OutcomeLedgerDocument.document_id(account_id, post_id)
        tracked_id = TrackedPostDocument.document_id(account_id, post_id)

        # IDs are co-locatable (same account-post pair)
        assert ledger_id.endswith(f"{account_id}-{post_id}")
        assert tracked_id.endswith(f"{account_id}-{post_id}")

    def test_full_attribution_flow_mockup(self) -> None:
        """
        Mock the full flow:
        1. runner.py creates PostCreationMetrics with run_id + pipeline_hash
        2. post_tick.py stamps OutcomeLedgerDocument
        3. engagement_job.py updates outcome with metrics
        """
        # Step 1: Runner creates metrics
        account_id = "JohnJames_News"
        post_id = "tweet_123"
        run_id = "run_abc123"
        pipeline_hash = "pipe_xyz789"
        soul_hash = "soul_v1"

        creation_metrics = PostCreationMetrics(
            candidates_created=1,
            tweets_pulled=5,
            voice_version_hash=soul_hash,
            run_id=run_id,
            pipeline_hash=pipeline_hash,
        )

        # Step 2: post_tick.py calls stamp
        ledger_doc = OutcomeLedgerDocument(
            account_id=account_id,
            post_id=post_id,
            run_id=creation_metrics.run_id,
            soul_hash=creation_metrics.voice_version_hash,
            pipeline_hash=creation_metrics.pipeline_hash,
            reward=None,  # Not yet
            raw_metrics={},
        )

        # Verify header is in place
        assert ledger_doc.run_id == run_id
        assert ledger_doc.soul_hash == soul_hash
        assert ledger_doc.pipeline_hash == pipeline_hash
        assert ledger_doc.reward is None

        # Step 3: engagement_job polls and updates
        latest_metrics = {
            "impression_count": 500,
            "engagement_rate": 0.04,
            "like_count": 20,
            "reply_count": 0,
        }
        new_reward = compute_reward(latest_metrics)

        # Simulate the ledger.update_outcome() operation
        ledger_doc.raw_metrics = latest_metrics
        ledger_doc.reward = new_reward

        # Verify ledger now has reward + metrics, header unchanged
        assert ledger_doc.reward == 0.04
        assert ledger_doc.raw_metrics["engagement_rate"] == 0.04
        assert ledger_doc.run_id == run_id  # Unchanged
        assert ledger_doc.pipeline_hash == pipeline_hash  # Unchanged
        assert ledger_doc.soul_hash == soul_hash  # Unchanged

    def test_multiple_posts_same_pipeline_can_be_grouped(self) -> None:
        """Multiple posts from the same pipeline_hash are groupable for evaluation."""
        pipeline_hash = "pipe_v1"

        # Two posts from the same pipeline version
        ledger_docs = [
            OutcomeLedgerDocument(
                account_id="test",
                post_id="post_1",
                pipeline_hash=pipeline_hash,
                reward=0.05,
            ),
            OutcomeLedgerDocument(
                account_id="test",
                post_id="post_2",
                pipeline_hash=pipeline_hash,
                reward=0.03,
            ),
        ]

        # Evaluator can group by pipeline_hash
        by_hash = {}
        for doc in ledger_docs:
            if doc.pipeline_hash not in by_hash:
                by_hash[doc.pipeline_hash] = []
            by_hash[doc.pipeline_hash].append(doc)

        assert len(by_hash[pipeline_hash]) == 2
        rewards = [d.reward for d in by_hash[pipeline_hash] if d.reward]
        assert sum(rewards) / len(rewards) == 0.04  # average

"""Unit tests for reward function: normalized per-post reward and account averages."""

import pytest

from app.reward.reward_function import (
    post_reward,
    account_avg_reward,
    _saturate,
    _num,
    ENG_RATE_REFERENCE,
    W_ENGAGEMENT,
    W_VELOCITY,
    W_REPLY,
)


# --- Saturate function tests ---


def test_saturate_zero() -> None:
    """x=0 should map to 0."""
    assert _saturate(0.0, 0.05) == 0.0


def test_saturate_reference() -> None:
    """x=ref should map to 0.5."""
    assert _saturate(ENG_RATE_REFERENCE, ENG_RATE_REFERENCE) == 0.5


def test_saturate_monotonic() -> None:
    """Saturate is strictly monotonic increasing."""
    ref = 0.05
    vals = [0.0, 0.01, 0.05, 0.1, 0.2, 1.0]
    saturated = [_saturate(v, ref) for v in vals]
    assert saturated == sorted(saturated)


def test_saturate_asymptote() -> None:
    """Saturate approaches 1 but never reaches it."""
    ref = 0.05
    assert _saturate(100.0, ref) < 1.0
    assert _saturate(1000.0, ref) < 1.0
    assert _saturate(1000000.0, ref) > 0.99


def test_saturate_negative() -> None:
    """Negative x should map to 0."""
    assert _saturate(-0.1, 0.05) == 0.0


# --- Numeric coercion tests ---


def test_num_int() -> None:
    """Int should coerce to float."""
    assert _num(5) == 5.0


def test_num_float() -> None:
    """Float should pass through."""
    assert _num(5.5) == 5.5


def test_num_bool_false() -> None:
    """Bool False should coerce to 0 (not 1 for True)."""
    assert _num(False) == 0.0
    assert _num(True) == 0.0


def test_num_none() -> None:
    """None should coerce to 0."""
    assert _num(None) == 0.0


def test_num_string() -> None:
    """String should coerce to 0."""
    assert _num("5") == 0.0


# --- Edge case: insufficient data ---


def test_post_reward_no_impressions() -> None:
    """impression_count missing => None."""
    assert post_reward({}) is None


def test_post_reward_zero_impressions() -> None:
    """impression_count == 0 => None (insufficient data)."""
    assert post_reward({"impression_count": 0}) is None


def test_post_reward_negative_impressions() -> None:
    """impression_count < 0 => None (nonsense)."""
    assert post_reward({"impression_count": -1}) is None


def test_post_reward_impression_bool() -> None:
    """impression_count == True/False => None (bool excluded)."""
    assert post_reward({"impression_count": True}) is None
    assert post_reward({"impression_count": False}) is None


# --- Edge case: zero engagement, nonzero reach ---


def test_post_reward_zero_engagement() -> None:
    """Post with reach but zero engagement should yield a real number near 0."""
    row = {
        "impression_count": 100,
        "like_count": 0,
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
    }
    reward = post_reward(row)
    assert reward is not None
    assert 0.0 <= reward <= 1.0
    # With zero engagement, R_engagement=0, R_reply=0, so full weight on zeroes.
    assert reward == 0.0


def test_post_reward_zero_engagement_with_velocity() -> None:
    """Post with reach, zero engagement, but with velocity."""
    row = {
        "impression_count": 100,
        "like_count": 0,
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
        "engagement_velocity": 0.0,
    }
    reward = post_reward(row)
    assert reward is not None
    assert 0.0 <= reward <= 1.0
    assert reward == 0.0


# --- Basic engagement reward ---


def test_post_reward_engagement_reference() -> None:
    """engagement_rate == reference => R_engagement == 0.5."""
    row = {
        "impression_count": 100,
        "like_count": 5,  # engagement_rate = 5/100 = 0.05 == reference
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
    }
    reward = post_reward(row)
    assert reward is not None
    # R_engagement = 0.5, R_reply = 0 (no replies), no velocity.
    # denom = 0.60 + 0.15 = 0.75
    expected = (0.60 / 0.75) * 0.5 + (0.15 / 0.75) * 0.0
    assert abs(reward - expected) < 1e-9


def test_post_reward_high_engagement() -> None:
    """Higher engagement rate => higher reward."""
    row_low = {
        "impression_count": 100,
        "like_count": 5,  # engagement_rate = 0.05
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
    }
    row_high = {
        "impression_count": 100,
        "like_count": 10,  # engagement_rate = 0.10
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
    }
    reward_low = post_reward(row_low)
    reward_high = post_reward(row_high)
    assert reward_low is not None
    assert reward_high is not None
    assert reward_high > reward_low


# --- Reply share (R_reply) ---


def test_post_reward_reply_share_zero() -> None:
    """No replies => R_reply = 0."""
    row = {
        "impression_count": 100,
        "like_count": 10,
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
    }
    reward = post_reward(row)
    assert reward is not None
    # R_engagement = _saturate(0.10, 0.05) ≈ 0.667
    # R_reply = 0 / 10 = 0
    # denom = 0.75, reward = (0.60/0.75) * 0.667 ≈ 0.533
    r_eng = _saturate(0.10, 0.05)
    expected = (0.60 / 0.75) * r_eng
    assert abs(reward - expected) < 1e-9


def test_post_reward_reply_share_half() -> None:
    """Half replies => R_reply = 0.5."""
    row = {
        "impression_count": 100,
        "like_count": 5,
        "reply_count": 5,
        "retweet_count": 0,
        "quote_count": 0,
    }
    reward = post_reward(row)
    assert reward is not None
    # R_engagement = _saturate(0.10, 0.05)
    # R_reply = 5 / 10 = 0.5
    # denom = 0.75
    r_eng = _saturate(0.10, 0.05)
    expected = (0.60 / 0.75) * r_eng + (0.15 / 0.75) * 0.5
    assert abs(reward - expected) < 1e-9


def test_post_reward_reply_share_all() -> None:
    """All replies => R_reply = 1.0."""
    row = {
        "impression_count": 100,
        "like_count": 0,
        "reply_count": 10,
        "retweet_count": 0,
        "quote_count": 0,
    }
    reward = post_reward(row)
    assert reward is not None
    # R_engagement = _saturate(0.10, 0.05)
    # R_reply = 10 / 10 = 1.0
    # denom = 0.75
    r_eng = _saturate(0.10, 0.05)
    expected = (0.60 / 0.75) * r_eng + (0.15 / 0.75) * 1.0
    assert abs(reward - expected) < 1e-9


# --- Velocity present ---


def test_post_reward_velocity_present() -> None:
    """With velocity, all three terms should be included."""
    row = {
        "impression_count": 100,
        "like_count": 10,
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
        "engagement_velocity": 0.05,  # equals reference
    }
    reward = post_reward(row)
    assert reward is not None
    r_eng = _saturate(0.10, 0.05)
    r_vel = _saturate(0.05, 0.05)  # reference => 0.5
    r_reply = 0.0
    expected = W_ENGAGEMENT * r_eng + W_VELOCITY * r_vel + W_REPLY * r_reply
    assert abs(reward - expected) < 1e-9


def test_post_reward_velocity_absent() -> None:
    """Without velocity, weights should renormalize to 0.75 denom."""
    row = {
        "impression_count": 100,
        "like_count": 10,
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
    }
    reward = post_reward(row)
    assert reward is not None
    r_eng = _saturate(0.10, 0.05)
    r_reply = 0.0
    denom = W_ENGAGEMENT + W_REPLY
    expected = (W_ENGAGEMENT / denom) * r_eng + (W_REPLY / denom) * r_reply
    assert abs(reward - expected) < 1e-9


def test_post_reward_velocity_vs_absent() -> None:
    """Identical counts with/without velocity should differ."""
    row_base = {
        "impression_count": 100,
        "like_count": 10,
        "reply_count": 5,
        "retweet_count": 0,
        "quote_count": 0,
    }
    row_with_vel = {**row_base, "engagement_velocity": 0.10}
    reward_absent = post_reward(row_base)
    reward_with_vel = post_reward(row_with_vel)
    assert reward_absent is not None
    assert reward_with_vel is not None
    # With velocity at 0.10 (higher than engagement_rate 0.15):
    # R_vel = 0.10 / (0.10 + 0.05) = 0.667
    # This should increase the overall reward.
    assert reward_with_vel > reward_absent


def test_post_reward_velocity_none_skipped() -> None:
    """engagement_velocity == None should be handled as absent."""
    row = {
        "impression_count": 100,
        "like_count": 10,
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
        "engagement_velocity": None,
    }
    reward = post_reward(row)
    assert reward is not None
    r_eng = _saturate(0.10, 0.05)
    denom = W_ENGAGEMENT + W_REPLY
    expected = (W_ENGAGEMENT / denom) * r_eng
    assert abs(reward - expected) < 1e-9


def test_post_reward_velocity_bool_skipped() -> None:
    """engagement_velocity == bool should be treated as absent."""
    row = {
        "impression_count": 100,
        "like_count": 10,
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
        "engagement_velocity": True,
    }
    reward = post_reward(row)
    assert reward is not None
    # Bool should be ignored, weights renormalized.
    r_eng = _saturate(0.10, 0.05)
    denom = W_ENGAGEMENT + W_REPLY
    expected = (W_ENGAGEMENT / denom) * r_eng
    assert abs(reward - expected) < 1e-9


# --- Engagement rate recomputation ---


def test_post_reward_engagement_rate_stored() -> None:
    """If engagement_rate is stored, should use it."""
    row = {
        "impression_count": 100,
        "like_count": 10,
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
        "engagement_rate": 0.15,
    }
    reward = post_reward(row)
    assert reward is not None
    r_eng = _saturate(0.15, 0.05)
    denom = W_ENGAGEMENT + W_REPLY
    expected = (W_ENGAGEMENT / denom) * r_eng
    assert abs(reward - expected) < 1e-9


def test_post_reward_engagement_rate_missing() -> None:
    """If engagement_rate missing but counts present, should recompute."""
    row = {
        "impression_count": 100,
        "like_count": 10,
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
        # engagement_rate not stored
    }
    reward = post_reward(row)
    assert reward is not None
    # Recomputed rate = (10 + 0 + 0 + 0) / 100 = 0.10
    r_eng = _saturate(0.10, 0.05)
    denom = W_ENGAGEMENT + W_REPLY
    expected = (W_ENGAGEMENT / denom) * r_eng
    assert abs(reward - expected) < 1e-9


# --- Reward bounds ---


def test_post_reward_in_bounds_all_cases() -> None:
    """Every non-None reward should be in [0, 1]."""
    test_cases = [
        {"impression_count": 100, "like_count": 0, "reply_count": 0, "retweet_count": 0, "quote_count": 0},
        {"impression_count": 100, "like_count": 1, "reply_count": 0, "retweet_count": 0, "quote_count": 0},
        {"impression_count": 100, "like_count": 10, "reply_count": 0, "retweet_count": 0, "quote_count": 0},
        {"impression_count": 100, "like_count": 10, "reply_count": 5, "retweet_count": 0, "quote_count": 0},
        {"impression_count": 100, "like_count": 10, "reply_count": 0, "retweet_count": 5, "quote_count": 0},
        {"impression_count": 100, "like_count": 0, "reply_count": 10, "retweet_count": 0, "quote_count": 0},
        {"impression_count": 100, "like_count": 10, "reply_count": 0, "retweet_count": 0, "quote_count": 0, "engagement_velocity": 0.05},
        {"impression_count": 100, "like_count": 10, "reply_count": 0, "retweet_count": 0, "quote_count": 0, "engagement_velocity": 0.50},
    ]
    for row in test_cases:
        reward = post_reward(row)
        assert reward is not None, f"Unexpected None for row: {row}"
        assert 0.0 <= reward <= 1.0, f"Reward {reward} out of bounds for row: {row}"


# --- Account average ---


def test_account_avg_reward_empty() -> None:
    """Empty list => None."""
    assert account_avg_reward([]) is None


def test_account_avg_reward_all_insufficient() -> None:
    """All posts with insufficient data => None."""
    rows = [
        {},
        {"impression_count": 0},
        {"impression_count": -1},
    ]
    assert account_avg_reward(rows) is None


def test_account_avg_reward_single() -> None:
    """Single qualified post => that post's reward."""
    row = {
        "impression_count": 100,
        "like_count": 5,  # engagement_rate = 0.05
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
    }
    avg = account_avg_reward([row])
    individual = post_reward(row)
    assert abs(avg - individual) < 1e-9


def test_account_avg_reward_mixed() -> None:
    """Mix of qualified and unqualified => average of qualified only."""
    rows = [
        {},  # insufficient
        {"impression_count": 100, "like_count": 5, "reply_count": 0, "retweet_count": 0, "quote_count": 0},  # 0.05 rate
        {"impression_count": 100, "like_count": 10, "reply_count": 0, "retweet_count": 0, "quote_count": 0},  # 0.10 rate
        {"impression_count": 0},  # insufficient
    ]
    avg = account_avg_reward(rows)
    assert avg is not None
    r1 = post_reward(rows[1])
    r2 = post_reward(rows[2])
    expected_avg = (r1 + r2) / 2
    assert abs(avg - expected_avg) < 1e-9


def test_account_avg_reward_multiple() -> None:
    """Multiple posts should average correctly."""
    rows = [
        {"impression_count": 100, "like_count": 5, "reply_count": 0, "retweet_count": 0, "quote_count": 0},
        {"impression_count": 100, "like_count": 10, "reply_count": 0, "retweet_count": 0, "quote_count": 0},
        {"impression_count": 100, "like_count": 3, "reply_count": 2, "retweet_count": 0, "quote_count": 0},
    ]
    avg = account_avg_reward(rows)
    assert avg is not None
    rewards = [post_reward(row) for row in rows]
    expected_avg = sum(r for r in rewards if r is not None) / len([r for r in rewards if r is not None])
    assert abs(avg - expected_avg) < 1e-9


# --- Deleted posts (should be treated normally) ---


def test_post_reward_deleted_post() -> None:
    """Deleted post with metrics should still yield a reward."""
    row = {
        "is_deleted": True,
        "impression_count": 100,
        "like_count": 5,
        "reply_count": 0,
        "retweet_count": 0,
        "quote_count": 0,
    }
    reward = post_reward(row)
    assert reward is not None
    # Reward should be computed from the last-known metrics, not affected by is_deleted flag.


# --- Integration: complete realistic scenario ---


def test_complete_account_scenario() -> None:
    """Realistic account with diverse posts."""
    rows = [
        {
            "impression_count": 500,
            "like_count": 50,
            "reply_count": 10,
            "retweet_count": 20,
            "quote_count": 5,
            "engagement_velocity": 0.08,
        },
        {
            "impression_count": 200,
            "like_count": 5,
            "reply_count": 2,
            "retweet_count": 1,
            "quote_count": 0,
            "engagement_velocity": 0.02,
        },
        {
            "impression_count": 100,
            "like_count": 0,
            "reply_count": 0,
            "retweet_count": 0,
            "quote_count": 0,
        },
        {},  # No impressions, excluded
    ]
    avg = account_avg_reward(rows)
    assert avg is not None
    assert 0.0 <= avg <= 1.0
    # Should be average of first 3 posts
    individual_rewards = [post_reward(row) for row in rows[:3]]
    assert all(r is not None for r in individual_rewards)
    expected_avg = sum(individual_rewards) / 3
    assert abs(avg - expected_avg) < 1e-9

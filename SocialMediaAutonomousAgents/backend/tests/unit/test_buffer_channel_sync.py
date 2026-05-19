from app.models.account import AccountDocument
from app.services.buffer_channel_sync import (
    is_buffer_x_channel,
    pick_best_x_channel,
    score_account_to_x_channel,
)


def test_is_buffer_x_channel():
    assert is_buffer_x_channel({"service": "twitter"})
    assert is_buffer_x_channel({"service": "X"})
    assert not is_buffer_x_channel({"service": "instagram"})


def test_score_account_to_x_channel_handle_in_name():
    acc = AccountDocument(account_id="JohnJames_News", niche="n", twitter_handle="@JohnJames_News")
    ch = {"id": "1", "name": "JohnJames News", "service": "twitter"}
    assert score_account_to_x_channel(acc, ch) >= 75


def test_pick_best_x_channel_unique():
    acc = AccountDocument(account_id="foo", niche="n", twitter_handle="@foo")
    channels = [
        {"id": "a", "name": "Instagram", "service": "instagram"},
        {"id": "b", "name": "foo account", "service": "twitter"},
    ]
    got = pick_best_x_channel(acc, channels)
    assert got is not None
    assert got["id"] == "b"


def test_pick_best_x_channel_tie_returns_none():
    acc = AccountDocument(account_id="foo", niche="n", twitter_handle="@foo")
    channels = [
        {"id": "1", "name": "foo", "service": "twitter"},
        {"id": "2", "name": "foo", "service": "twitter"},
    ]
    assert pick_best_x_channel(acc, channels) is None

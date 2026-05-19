"""Tweet media and embed URL extraction."""

from app.social.tweet_enrichment import (
    append_url_to_post_body,
    enrich_tweet,
    filter_rows_with_urls,
    row_has_native_media_url,
    row_has_url,
    select_chosen_post_embed_url,
    select_chosen_post_media_url,
    select_post_append_url,
    tweet_permalink,
)


def test_tweet_permalink_numeric_id() -> None:
    assert tweet_permalink("2056147803630715100") == "https://x.com/i/status/2056147803630715100"
    assert tweet_permalink("trend:ai") is None


def test_enrich_tweet_video_and_external_url() -> None:
    tweet = {
        "id": "100",
        "attachments": {"media_keys": ["m1"]},
        "entities": {
            "urls": [
                {
                    "url": "https://t.co/abc",
                    "expanded_url": "https://www.youtube.com/watch?v=xyz",
                    "display_url": "youtube.com/watch?v=xyz",
                }
            ]
        },
    }
    includes = {
        "media": [
            {
                "media_key": "m1",
                "type": "video",
                "url": "https://video.twimg.com/ext_tw_video/1.mp4",
                "preview_image_url": "https://pbs.twimg.com/thumb.jpg",
            }
        ]
    }
    e = enrich_tweet(tweet, includes)
    assert e.primary_media_type == "video"
    assert e.media_types == ["video"]
    assert len(e.media) == 1
    assert e.media[0].type == "video"
    assert "https://x.com/i/status/100" in e.embed_urls
    assert "https://www.youtube.com/watch?v=xyz" in e.embed_urls
    assert not any("video.twimg.com" in u for u in e.embed_urls)
    assert not any("pbs.twimg.com" in u for u in e.embed_urls)


def test_enrich_excludes_x_status_expanded_url_duplicate() -> None:
    tweet = {
        "id": "200",
        "entities": {
            "urls": [
                {
                    "url": "https://t.co/x",
                    "expanded_url": "https://x.com/otheruser/status/999",
                }
            ]
        },
    }
    e = enrich_tweet(tweet, None)
    assert e.embed_urls == ["https://x.com/i/status/200"]


def test_row_has_url_external_entity() -> None:
    row = {
        "text": "hello",
        "url_entities": [{"url": "https://t.co/x", "expanded_url": "https://example.com/a"}],
        "embed_urls": ["https://x.com/i/status/1"],
    }
    assert row_has_url(row) is True


def test_row_has_url_permalink_only_excluded() -> None:
    row = {
        "text": "no link here",
        "embed_urls": ["https://x.com/i/status/1"],
        "tweet_permalink": "https://x.com/i/status/1",
    }
    assert row_has_url(row) is False


def test_filter_rows_with_urls() -> None:
    rows = [
        {"id": "1", "text": "see https://news.com/x"},
        {"id": "2", "text": "plain", "embed_urls": ["https://x.com/i/status/2"]},
    ]
    assert len(filter_rows_with_urls(rows)) == 1
    assert filter_rows_with_urls(rows)[0]["id"] == "1"


def test_row_has_url_includes_native_media() -> None:
    row = {
        "text": "photo only",
        "media": [{"type": "photo", "url": "https://pbs.twimg.com/media/abc.jpg"}],
        "embed_urls": ["https://x.com/i/status/1"],
    }
    assert row_has_native_media_url(row) is True
    assert row_has_url(row) is True


def test_select_chosen_post_media_url_native_media_uses_status_card() -> None:
    row = {
        "id": "100",
        "tweet_permalink": "https://x.com/i/status/100",
        "media": [
            {"type": "photo", "url": "https://pbs.twimg.com/photo.jpg"},
            {
                "type": "video",
                "url": "https://video.twimg.com/ext_tw_video/1.mp4",
                "preview_image_url": "https://pbs.twimg.com/thumb.jpg",
            },
        ],
    }
    assert select_chosen_post_media_url(row) == "https://x.com/i/status/100"


def test_select_chosen_post_media_url_photo_uses_status_card() -> None:
    row = {
        "id": "101",
        "tweet_permalink": "https://x.com/i/status/101",
        "media": [{"type": "photo", "url": "https://pbs.twimg.com/media/xyz.jpg"}],
    }
    assert select_chosen_post_media_url(row) == "https://x.com/i/status/101"


def test_select_chosen_post_media_url_external_not_status() -> None:
    row = {
        "id": "99",
        "tweet_permalink": "https://x.com/i/status/99",
        "url_entities": [{"expanded_url": "https://example.com/story"}],
        "embed_urls": ["https://x.com/i/status/99", "https://example.com/story"],
    }
    assert select_chosen_post_media_url(row) == "https://example.com/story"
    assert select_chosen_post_embed_url(row) == "https://x.com/i/status/99"


def test_select_chosen_post_media_url_status_only() -> None:
    row = {
        "id": "88",
        "tweet_permalink": "https://x.com/i/status/88",
        "embed_urls": ["https://x.com/i/status/88"],
    }
    assert select_chosen_post_media_url(row) == "https://x.com/i/status/88"
    assert select_post_append_url(row) == "https://x.com/i/status/88"


def test_select_chosen_post_embed_url_uses_permalink_not_external() -> None:
    row = {
        "id": "99",
        "tweet_permalink": "https://x.com/i/status/99",
        "url_entities": [{"expanded_url": "https://example.com/story"}],
        "embed_urls": ["https://x.com/i/status/99", "https://example.com/story"],
    }
    assert select_chosen_post_embed_url(row) == "https://x.com/i/status/99"
    assert select_post_append_url(row) == "https://example.com/story"


def test_select_chosen_post_embed_url_from_id_only() -> None:
    row = {"tweet_id": "2056170982784602538"}
    assert select_chosen_post_embed_url(row) == "https://x.com/i/status/2056170982784602538"


def test_select_post_append_url_prefers_external() -> None:
    row = {
        "id": "99",
        "tweet_permalink": "https://x.com/i/status/99",
        "url_entities": [{"expanded_url": "https://example.com/story"}],
        "embed_urls": ["https://x.com/i/status/99", "https://example.com/story"],
    }
    assert select_post_append_url(row) == "https://example.com/story"


def test_select_post_append_url_falls_back_to_permalink() -> None:
    row = {
        "id": "88",
        "tweet_permalink": "https://x.com/i/status/88",
        "embed_urls": ["https://x.com/i/status/88"],
    }
    assert select_post_append_url(row) == "https://x.com/i/status/88"


def test_append_url_to_post_body() -> None:
    body = "Breaking news update."
    url = "https://example.com/story"
    out = append_url_to_post_body(body, url)
    assert out.endswith(url)
    assert "\n\n" in out

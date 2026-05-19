from app.social.trend_query import build_search_query, trend_keywords, tweet_matches_trend


def test_build_search_query_hashtag():
    q = build_search_query("#BorderCrisis")
    assert "#BorderCrisis" in q
    assert "-is:retweet" in q


def test_build_search_query_phrase():
    q = build_search_query("Congress AI")
    assert '"Congress AI"' in q
    assert "-is:retweet" in q


def test_tweet_matches_trend_keywords():
    assert tweet_matches_trend("Big AI policy vote today", "AI policy")
    assert not tweet_matches_trend("Sports recap only", "AI policy")

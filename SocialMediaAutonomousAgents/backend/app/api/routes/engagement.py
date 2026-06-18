from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.infrastructure.ravendb_http import RavenDBHttpError
from app.services.account_repository import AccountRepository
from app.services.twitter_service import TwitterService
from app.social.exceptions import SocialPlatformError

router = APIRouter()
repo = AccountRepository()
twitter = TwitterService(repo=repo)


# ── Request/Response Models ────────────────────────────────────────────────────


class LikeBody(BaseModel):
    """POST body for liking a tweet."""

    account_id: str = Field(..., description="Account ID of the user liking the tweet")
    tweet_id: str = Field(..., description="Tweet ID to like")


class RetweetBody(BaseModel):
    """POST body for retweeting a tweet."""

    account_id: str = Field(..., description="Account ID of the user retweeting")
    tweet_id: str = Field(..., description="Tweet ID to retweet")


class FollowBody(BaseModel):
    """POST body for following a user."""

    account_id: str = Field(..., description="Account ID of the user following")
    user_id: str = Field(..., description="User ID to follow")


class QuoteBody(BaseModel):
    """POST body for quoting a tweet."""

    account_id: str = Field(..., description="Account ID of the user quoting")
    quoted_tweet_id: str = Field(..., description="Tweet ID being quoted")
    text: str = Field(..., min_length=1, description="Quote text")


# ── Likes ──────────────────────────────────────────────────────────────────────


@router.post("/engagement/like", status_code=201)
def like_tweet(body: LikeBody):
    """Like a tweet."""
    try:
        result = twitter.like_tweet(body.account_id, body.tweet_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    except SocialPlatformError as exc:
        raise HTTPException(status_code=503, detail=f"X API error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error liking tweet: {exc}") from exc
    return {"ok": True, "tweet_id": body.tweet_id, "result": result}


@router.delete("/engagement/like/{tweet_id}")
def unlike_tweet(
    tweet_id: str,
    account_id: str = Query(..., description="Account ID of the user unliking the tweet"),
):
    """Unlike a tweet."""
    try:
        result = twitter.unlike_tweet(account_id, tweet_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    except SocialPlatformError as exc:
        raise HTTPException(status_code=503, detail=f"X API error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error unliking tweet: {exc}") from exc
    return {"ok": True, "tweet_id": tweet_id, "result": result}


@router.get("/engagement/post/{tweet_id}/likers")
def get_post_likers(
    tweet_id: str,
    account_id: str = Query(..., description="Account ID to use for API auth"),
    max_results: int = Query(default=10, ge=1, le=100, description="Max likers to fetch"),
):
    """Fetch users who liked a specific post."""
    try:
        likers = twitter.get_tweet_likers(account_id, tweet_id, max_results=max_results)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    except SocialPlatformError as exc:
        raise HTTPException(status_code=503, detail=f"X API error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching likers: {exc}") from exc
    return {"tweet_id": tweet_id, "liker_count": len(likers), "likers": likers}


# ── Retweets ───────────────────────────────────────────────────────────────────


@router.post("/engagement/retweet", status_code=201)
def retweet_tweet(body: RetweetBody):
    """Retweet a tweet."""
    try:
        result = twitter.retweet_tweet(body.account_id, body.tweet_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    except SocialPlatformError as exc:
        raise HTTPException(status_code=503, detail=f"X API error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error retweeting: {exc}") from exc
    return {"ok": True, "tweet_id": body.tweet_id, "result": result}


@router.delete("/engagement/retweet/{tweet_id}")
def unretweet_tweet(
    tweet_id: str,
    account_id: str = Query(..., description="Account ID of the user unretweeting"),
):
    """Remove a retweet."""
    try:
        result = twitter.unretweet_tweet(account_id, tweet_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    except SocialPlatformError as exc:
        raise HTTPException(status_code=503, detail=f"X API error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error removing retweet: {exc}") from exc
    return {"ok": True, "tweet_id": tweet_id, "result": result}


@router.get("/engagement/post/{tweet_id}/retweeters")
def get_post_retweeters(
    tweet_id: str,
    account_id: str = Query(..., description="Account ID to use for API auth"),
    max_results: int = Query(default=10, ge=1, le=100, description="Max retweeters to fetch"),
):
    """Fetch users who retweeted a specific post."""
    try:
        retweeters = twitter.get_tweet_retweeters(account_id, tweet_id, max_results=max_results)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    except SocialPlatformError as exc:
        raise HTTPException(status_code=503, detail=f"X API error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching retweeters: {exc}") from exc
    return {"tweet_id": tweet_id, "retweeter_count": len(retweeters), "retweeters": retweeters}


# ── Follows ────────────────────────────────────────────────────────────────────


@router.post("/engagement/follow", status_code=201)
def follow_user(body: FollowBody):
    """Follow a user."""
    try:
        result = twitter.follow_user(body.account_id, body.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    except SocialPlatformError as exc:
        raise HTTPException(status_code=503, detail=f"X API error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error following user: {exc}") from exc
    return {"ok": True, "user_id": body.user_id, "result": result}


@router.delete("/engagement/follow/{user_id}")
def unfollow_user(
    user_id: str,
    account_id: str = Query(..., description="Account ID of the user unfollowing"),
):
    """Unfollow a user."""
    try:
        result = twitter.unfollow_user(account_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    except SocialPlatformError as exc:
        raise HTTPException(status_code=503, detail=f"X API error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error unfollowing user: {exc}") from exc
    return {"ok": True, "user_id": user_id, "result": result}


# ── Quotes ─────────────────────────────────────────────────────────────────────


@router.post("/engagement/quote", status_code=201)
def quote_tweet(body: QuoteBody):
    """Quote a tweet."""
    try:
        result = twitter.quote_tweet(body.account_id, body.quoted_tweet_id, body.text)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    except SocialPlatformError as exc:
        raise HTTPException(status_code=503, detail=f"X API error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error quoting tweet: {exc}") from exc
    return {"ok": True, "quoted_tweet_id": body.quoted_tweet_id, "result": result}


@router.get("/engagement/post/{tweet_id}/quotes")
def get_post_quotes(
    tweet_id: str,
    account_id: str = Query(..., description="Account ID to use for API auth"),
    max_results: int = Query(default=10, ge=1, le=100, description="Max quotes to fetch"),
):
    """Fetch quote tweets for a specific post."""
    try:
        quotes = twitter.get_tweet_quotes(account_id, tweet_id, max_results=max_results)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    except SocialPlatformError as exc:
        raise HTTPException(status_code=503, detail=f"X API error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching quotes: {exc}") from exc
    return {"tweet_id": tweet_id, "quote_count": len(quotes), "quotes": quotes}


# ── Search Archive ─────────────────────────────────────────────────────────────


@router.get("/search/archive")
def search_archive(
    account_id: str = Query(..., description="Account ID to search as"),
    query: str = Query(..., description="Search query"),
    start_time: str | None = Query(default=None, description="Start time (ISO 8601 format)"),
    end_time: str | None = Query(default=None, description="End time (ISO 8601 format)"),
    max_results: int = Query(default=10, ge=1, le=100, description="Max results to fetch"),
):
    """Search the archive for tweets matching a query within an optional time range."""
    try:
        results = twitter.search_archive(
            account_id,
            query,
            start_time=start_time,
            end_time=end_time,
            max_results=max_results,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    except SocialPlatformError as exc:
        raise HTTPException(status_code=503, detail=f"X API error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error searching archive: {exc}") from exc
    return {"query": query, "result_count": len(results), "results": results}

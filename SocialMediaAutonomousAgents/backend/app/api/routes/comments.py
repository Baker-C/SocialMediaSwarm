from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.infrastructure.ravendb_http import RavenDBHttpError
from app.services.account_repository import AccountRepository
from app.services.twitter_service import TwitterService
from app.social.exceptions import SocialPlatformError

router = APIRouter()
repo = AccountRepository()
twitter = TwitterService(repo=repo)


class ReplyBody(BaseModel):
    """POST body for creating a reply."""

    account_id: str = Field(..., description="Account ID of the replying user")
    tweet_id: str = Field(..., description="Tweet ID to reply to")
    text: str = Field(..., min_length=1, description="Reply text")


@router.get("/comments/post/{tweet_id}")
def get_post_comments(
    tweet_id: str,
    account_id: str = Query(..., description="Account ID to use for API auth"),
    max_results: int = Query(default=10, ge=1, le=100, description="Max comments to fetch"),
):
    """Fetch comments/replies on a specific post."""
    try:
        comments = twitter.get_tweet_replies(account_id, tweet_id, max_results=max_results)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    except SocialPlatformError as exc:
        raise HTTPException(status_code=503, detail=f"X API error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error fetching comments: {exc}") from exc
    return {"tweet_id": tweet_id, "comment_count": len(comments), "comments": comments}


@router.post("/comments/reply", status_code=201)
def post_reply(body: ReplyBody):
    """Post a reply to a tweet."""
    try:
        reply = twitter.reply_to_tweet(body.account_id, body.tweet_id, body.text)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB error: {exc}") from exc
    except SocialPlatformError as exc:
        raise HTTPException(status_code=503, detail=f"X API error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error posting reply: {exc}") from exc
    return {"ok": True, "reply_id": reply["id"], "reply": reply}

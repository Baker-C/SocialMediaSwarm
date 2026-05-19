"""Public exports for the social / multi-platform layer."""

from app.social.credentials import XCredentials, XOAuth1Credentials, XOAuth2UserCredentials
from app.social.dtos import AccountData, CreatedPost, PostData, TrendItem, TrendsResult
from app.social.enums import SocialPlatform
from app.social.exceptions import SocialPlatformError
from app.social.protocol import SocialMediaClient
from app.social.service import SocialMediaService, get_social_media_service

__all__ = [
    "AccountData",
    "CreatedPost",
    "PostData",
    "SocialMediaClient",
    "SocialMediaService",
    "SocialPlatform",
    "SocialPlatformError",
    "TrendItem",
    "TrendsResult",
    "XCredentials",
    "XOAuth1Credentials",
    "XOAuth2UserCredentials",
    "get_social_media_service",
]

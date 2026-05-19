"""Platforms supported by the unified social facade (extend with new enum members)."""

from enum import Enum


class SocialPlatform(str, Enum):
    X = "x"

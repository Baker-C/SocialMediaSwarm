"""Errors raised by social platform implementations."""


class SocialPlatformError(RuntimeError):
    """API, auth, or mapping failure for a social network."""

    def __init__(self, message: str, *, vendor: str | None = None, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.vendor = vendor
        self.cause = cause

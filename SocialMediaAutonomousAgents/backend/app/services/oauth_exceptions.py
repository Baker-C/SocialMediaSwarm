"""OAuth 2.0 errors from X token endpoint and re-authorization signals."""


class XOAuthError(Exception):
    """Error JSON returned by POST /2/oauth2/token."""

    def __init__(
        self,
        error: str,
        error_description: str | None = None,
        *,
        http_status: int | None = None,
    ) -> None:
        self.error = (error or "unknown_error").strip()
        self.error_description = (error_description or "").strip() or None
        self.http_status = http_status
        desc = f": {self.error_description}" if self.error_description else ""
        super().__init__(f"X OAuth error {self.error}{desc}")


class ReauthRequired(Exception):
    """Stored refresh token is invalid; user must complete OAuth again."""

    def __init__(self, account_id: str, message: str | None = None) -> None:
        self.account_id = (account_id or "").strip()
        default = (
            f"X account {self.account_id} requires re-authorization. "
            "Connect again via GET /api/oauth/x/authorize."
        )
        super().__init__(message or default)

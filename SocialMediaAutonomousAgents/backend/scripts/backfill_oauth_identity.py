#!/usr/bin/env python3
"""Backfill x_user_id / x_username on OAuth2 tokens and surface identity collisions.

Part of the oauth-per-account-binding fix (PLAN.md section 4). For every token whose
``x_user_id`` and/or ``x_username`` is null, this resolves the real X identity from the
stored access token (refreshing first if expired) and writes it back -- but ONLY for rows
that resolve cleanly to a UNIQUE x_user_id. It never deletes tokens, never fabricates an
identity, and refuses to auto-resolve collision groups (one x_user_id bound to >1 account):
those require a human to pick the survivor.

Resolution order, per null-identity token:
  1. decrypt access token  (decrypt failure -> unresolved, skip, never delete)
  2. if expired and a refresh token exists -> refresh, then re-load
  3. GET https://api.x.com/2/users/me?user.fields=username with the access token
     (401/403/404 / suspended / empty data -> unresolved, leave null)
  4. clean resolve -> stage x_user_id + x_username

All tokens are loaded up front (RavenDB's index is eventually consistent), then resolved,
then -- only with --apply -- written. We never write-then-rescan in a single pass.

Usage::

    python scripts/backfill_oauth_identity.py            # dry-run (default): report only
    python scripts/backfill_oauth_identity.py --apply     # write clean unique rows
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import click
import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.oauth_token import OAuthTokenDocument  # noqa: E402
from app.services.account_repository import AccountRepository  # noqa: E402
from app.services.oauth_exceptions import ReauthRequired, XOAuthError  # noqa: E402
from app.services.oauth_token_repository import OAuthTokenRepository  # noqa: E402
from app.services.twitter_oauth2_service import TwitterOAuth2Service  # noqa: E402

USERS_ME_URL = "https://api.x.com/2/users/me?user.fields=username"


@dataclass
class RowResult:
    account_id: str
    status: str  # "resolved" | "already" | "unresolved"
    reason: str = ""
    x_user_id: str | None = None
    x_username: str | None = None
    will_write: bool = False
    token_updated_at: str | None = None
    account_last_post_at: str | None = None
    provisioning_x_user_id: str | None = None


@dataclass
class Backfill:
    service: TwitterOAuth2Service
    tokens: OAuthTokenRepository
    accounts: AccountRepository
    rows: list[RowResult] = field(default_factory=list)

    # ----- identity resolution -------------------------------------------------

    def _resolve_identity(self, access_token: str) -> tuple[str | None, str | None, str]:
        """Call users/me. Returns (x_user_id, x_username, reason).

        On any non-clean outcome both ids are None and reason explains why. We do NOT
        fabricate -- 401/403/404, suspended, or empty data all yield (None, None, ...).
        """
        try:
            with httpx.Client(timeout=20) as client:
                resp = client.get(
                    USERS_ME_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError as exc:
            return None, None, f"network error: {exc}"

        if resp.status_code in (401, 403):
            return None, None, f"users/me {resp.status_code} (revoked/forbidden)"
        if resp.status_code == 404:
            return None, None, "users/me 404 (not found)"
        if resp.status_code == 429:
            return None, None, "users/me 429 (rate limited)"
        if resp.status_code >= 400:
            return None, None, f"users/me http {resp.status_code}"

        try:
            payload = resp.json()
        except Exception:
            return None, None, "users/me response not JSON"
        if not isinstance(payload, dict):
            return None, None, "users/me response not an object"

        # A suspended/deactivated user comes back as errors with no usable data.
        data = payload.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            errors = payload.get("errors")
            detail = ""
            if isinstance(errors, list) and errors:
                detail = str(errors[0].get("detail") or errors[0].get("title") or "").strip()
            return None, None, f"users/me empty data{(' (' + detail + ')') if detail else ''}"

        x_user_id = str(data.get("id")).strip() or None
        x_username = str(data.get("username") or "").strip() or None
        if not x_user_id:
            return None, None, "users/me data missing id"
        return x_user_id, x_username, "resolved"

    def _decrypted_access(self, token: OAuthTokenDocument) -> tuple[str | None, str]:
        """Decrypt; on ValueError -> (None, reason). Refresh first when expired."""
        # Refresh if expired and a refresh token exists, so users/me sees a live token.
        if self._is_expired(token) and (token.refresh_token_enc or "").strip():
            try:
                if self.service.refresh_account_tokens(token.account_id):
                    reloaded = self.tokens.load_token(token.account_id)
                    if reloaded is not None:
                        token = reloaded
            except (ReauthRequired, XOAuthError) as exc:
                return None, f"refresh failed: {exc}"
            except Exception as exc:  # noqa: BLE001
                return None, f"refresh error: {exc}"

        try:
            access = self.service._decrypt(token.access_token_enc)
        except ValueError as exc:
            return None, f"decrypt failed: {exc}"
        if not access:
            return None, "decrypted access token empty"
        return access, "ok"

    def _is_expired(self, token: OAuthTokenDocument) -> bool:
        try:
            exp = datetime.fromisoformat((token.expires_at or "").replace("Z", "+00:00"))
        except Exception:
            return False
        return exp <= datetime.now(timezone.utc)

    # ----- account context (cheap, in-doc) -------------------------------------

    def _account_context(self, account_id: str) -> tuple[str | None, str | None]:
        """(last_post_at, provisioning.x_user_id) -- read straight from the account doc."""
        try:
            acc = self.accounts.load(account_id)
        except Exception:
            return None, None
        if acc is None:
            return None, None
        last_post = getattr(getattr(acc, "posting", None), "last_post_at", None)
        prov_id = getattr(getattr(acc, "provisioning", None), "x_user_id", None)
        return last_post, prov_id

    # ----- main pass -----------------------------------------------------------

    def run(self, *, apply: bool) -> None:
        all_tokens = self.tokens.list_tokens()
        click.echo(f"Loaded {len(all_tokens)} OAuth token(s).")

        # Pass 1: resolve. Stage results; do not write yet.
        for token in all_tokens:
            account_id = token.account_id
            last_post_at, prov_id = self._account_context(account_id)
            row = RowResult(
                account_id=account_id,
                status="unresolved",
                token_updated_at=token.updated_at,
                account_last_post_at=last_post_at,
                provisioning_x_user_id=prov_id,
                x_user_id=token.x_user_id,
                x_username=getattr(token, "x_username", None),
            )

            needs_id = not (token.x_user_id or "").strip()
            needs_username = not (getattr(token, "x_username", None) or "").strip()
            if not needs_id and not needs_username:
                row.status = "already"
                row.reason = "x_user_id and x_username already set"
                self.rows.append(row)
                continue

            access, dec_reason = self._decrypted_access(token)
            if access is None:
                row.reason = dec_reason
                self.rows.append(row)
                continue

            x_user_id, x_username, reason = self._resolve_identity(access)
            if x_user_id is None:
                row.reason = reason
                self.rows.append(row)
                continue

            row.status = "resolved"
            row.reason = reason
            row.x_user_id = x_user_id
            row.x_username = x_username
            self.rows.append(row)

        # Pass 2: collision detection across the FULL set (existing + newly resolved).
        id_to_accounts: dict[str, list[RowResult]] = defaultdict(list)
        for row in self.rows:
            if row.x_user_id:
                id_to_accounts[row.x_user_id].append(row)
        collisions = {xid: rs for xid, rs in id_to_accounts.items() if len({r.account_id for r in rs}) > 1}

        # Mark rows in a collision group so we never write them.
        colliding_account_ids = {r.account_id for rs in collisions.values() for r in rs}

        # Pass 3: decide writes -- only clean, resolved, UNIQUE rows.
        for row in self.rows:
            if row.status == "resolved" and row.account_id not in colliding_account_ids:
                row.will_write = True

        # Pass 4: report.
        self._print_report(collisions=collisions, apply=apply)

        # Pass 5: write (only with --apply), after all resolution is complete.
        if apply:
            self._write(colliding_account_ids=colliding_account_ids)
        else:
            click.echo("\nDRY RUN: no documents written. Re-run with --apply to persist clean unique rows.")

    def _write(self, *, colliding_account_ids: set[str]) -> None:
        written = 0
        for row in self.rows:
            if not row.will_write:
                continue
            token = self.tokens.load_token(row.account_id)
            if token is None:
                click.echo(f"  ! {row.account_id}: token vanished before write; skipping")
                continue
            data = token.model_dump()
            data["x_user_id"] = row.x_user_id
            data["x_username"] = row.x_username
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            # Re-validate so we tolerate the model gaining/lacking x_username.
            updated = OAuthTokenDocument.model_validate(
                {k: v for k, v in data.items() if k in OAuthTokenDocument.model_fields}
            )
            self.tokens.save_token(updated)
            written += 1
            click.echo(f"  + wrote {row.account_id}: x_user_id={row.x_user_id} x_username={row.x_username}")
        click.echo(f"\nAPPLIED: wrote identity for {written} token(s).")
        if colliding_account_ids:
            click.echo(
                f"SKIPPED {len(colliding_account_ids)} account(s) in collision groups -- "
                "resolve survivor manually (disconnect losers, reconnect each as its own X user)."
            )

    # ----- reporting -----------------------------------------------------------

    def _print_report(self, *, collisions: dict[str, list[RowResult]], apply: bool) -> None:
        resolved = [r for r in self.rows if r.status == "resolved"]
        already = [r for r in self.rows if r.status == "already"]
        unresolved = [r for r in self.rows if r.status == "unresolved"]
        will_write = [r for r in self.rows if r.will_write]

        click.echo("\n=== SUMMARY ===")
        click.echo(f"  total tokens     : {len(self.rows)}")
        click.echo(f"  already complete : {len(already)}")
        click.echo(f"  newly resolved   : {len(resolved)}")
        click.echo(f"  unresolved       : {len(unresolved)}")
        click.echo(f"  collision groups : {len(collisions)}")
        click.echo(f"  will write       : {len(will_write)} (mode={'APPLY' if apply else 'DRY-RUN'})")

        click.echo("\n=== PER-ROW STATUS ===")
        for row in sorted(self.rows, key=lambda r: r.account_id):
            mark = "WRITE" if row.will_write else ("OK   " if row.status == "already" else (
                "RESLV" if row.status == "resolved" else "UNRES"))
            ident = ""
            if row.x_user_id or row.x_username:
                ident = f" id={row.x_user_id or '-'} @{row.x_username or '-'}"
            click.echo(f"  [{mark}] {row.account_id}:{ident} {row.status} ({row.reason})")

        if collisions:
            click.echo("\n=== COLLISION GROUPS (x_user_id bound to >1 account) ===")
            click.echo("  REFUSING to auto-resolve. A human must pick the survivor per group.")
            for xid, rs in sorted(collisions.items()):
                accs = sorted({r.account_id for r in rs})
                click.echo(f"\n  x_user_id={xid}  ->  {len(accs)} accounts: {', '.join(accs)}")
                for row in sorted(rs, key=lambda r: r.account_id):
                    click.echo(
                        f"    - {row.account_id}: "
                        f"token_updated_at={row.token_updated_at or '-'} "
                        f"last_post_at={row.account_last_post_at or '-'} "
                        f"provisioning.x_user_id={row.provisioning_x_user_id or '-'}"
                    )


@click.command()
@click.option("--apply", "apply_", is_flag=True, default=False,
              help="Write resolved identities. Without this flag the script is dry-run (report only).")
def main(apply_: bool) -> None:
    """Backfill x_user_id/x_username on OAuth tokens; report identity collisions."""
    service = TwitterOAuth2Service()
    backfill = Backfill(
        service=service,
        tokens=service._tokens,
        accounts=service._accounts,
    )
    backfill.run(apply=apply_)


if __name__ == "__main__":
    main()

"""
Buffer GraphQL HTTP client (https://api.buffer.com).

Posting follows the official ``createPost`` flow: ``text``, ``channelId``,
``schedulingType: automatic``, ``mode: addToQueue`` — see
https://developers.buffer.com/guides/your-first-post.html
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BUFFER_GRAPHQL_URL = "https://api.buffer.com"


class BufferAPIError(RuntimeError):
    """GraphQL errors, HTTP failures, or unexpected Buffer payloads."""


def _escape_graphql_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n")


def buffer_graphql(
    api_key: str,
    query: str,
    *,
    variables: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """POST JSON ``{query, variables?}`` with ``Authorization: Bearer <api_key>``."""
    key = (api_key or "").strip()
    if not key:
        raise BufferAPIError("Buffer API key is empty")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {"query": query}
    if variables is not None:
        body["variables"] = variables
    with httpx.Client(timeout=timeout) as client:
        r = client.post(BUFFER_GRAPHQL_URL, headers=headers, json=body)
    try:
        payload = r.json()
    except Exception as exc:
        raise BufferAPIError(f"Buffer response is not JSON: HTTP {r.status_code} {r.text[:500]}") from exc
    if r.status_code >= 400:
        msg = _format_graphql_errors(payload) or r.text[:500]
        raise BufferAPIError(f"Buffer HTTP {r.status_code}: {msg}")
    errs = payload.get("errors")
    if isinstance(errs, list) and errs:
        raise BufferAPIError(_format_graphql_errors(payload) or "GraphQL errors")
    return payload


def _format_graphql_errors(payload: dict[str, Any]) -> str | None:
    errs = payload.get("errors")
    if not isinstance(errs, list) or not errs:
        return None
    parts: list[str] = []
    for e in errs:
        if isinstance(e, dict) and e.get("message"):
            parts.append(str(e["message"]))
        else:
            parts.append(repr(e))
    return "; ".join(parts)


def buffer_create_queued_post(api_key: str, channel_id: str, text: str) -> dict[str, Any]:
    """
    Queue a text post on the given Buffer channel (``mode: addToQueue``).

    Returns ``{"id": str, "text": str | None, "dueAt": str | None}`` for the Buffer post.
    """
    cid = (channel_id or "").strip()
    if not cid:
        raise BufferAPIError("buffer_channel_id is empty")
    if any(c in cid for c in '"\\\n\r'):
        raise BufferAPIError("buffer_channel_id contains invalid characters")

    esc_text = _escape_graphql_string(text)
    query = f"""mutation {{
  createPost(input: {{
    text: "{esc_text}"
    channelId: "{cid}"
    schedulingType: automatic
    mode: addToQueue
  }}) {{
    ... on PostActionSuccess {{
      post {{ id text dueAt }}
    }}
    ... on MutationError {{
      message
    }}
  }}
}}"""
    payload = buffer_graphql(api_key, query)
    data = payload.get("data") or {}
    cp = data.get("createPost")
    if not isinstance(cp, dict):
        raise BufferAPIError(f"Unexpected createPost payload: {cp!r}")

    if cp.get("message") and not cp.get("post"):
        raise BufferAPIError(str(cp["message"]))

    post = cp.get("post")
    if not isinstance(post, dict) or not post.get("id"):
        raise BufferAPIError(f"Unexpected createPost response: {cp!r}")

    return {"id": str(post["id"]), "text": post.get("text"), "dueAt": post.get("dueAt")}


def buffer_list_organizations(api_key: str) -> list[dict[str, Any]]:
    """Return ``[{id, name}, ...]`` for the authenticated Buffer account."""
    query = """query {
  account {
    organizations {
      id
      name
    }
  }
}"""
    payload = buffer_graphql(api_key, query)
    data = payload.get("data") or {}
    account = data.get("account")
    if not isinstance(account, dict):
        raise BufferAPIError(f"Unexpected account query payload: {data!r}")
    orgs = account.get("organizations")
    if not isinstance(orgs, list):
        return []
    return [o for o in orgs if isinstance(o, dict)]


def buffer_default_organization_id(api_key: str) -> str | None:
    """First organization id, or ``None`` if the account has no organizations."""
    orgs = buffer_list_organizations(api_key)
    if not orgs:
        return None
    oid = orgs[0].get("id")
    return str(oid).strip() if oid else None


def buffer_list_channels(api_key: str, organization_id: str) -> list[dict[str, Any]]:
    """List channels for a Buffer organization (``OrganizationId``)."""
    oid = (organization_id or "").strip()
    if not oid:
        raise BufferAPIError("organization_id is empty")
    ch_query = """query GetChannels($organizationId: OrganizationId!) {
  channels(input: { organizationId: $organizationId }) {
    id
    name
    service
  }
}"""
    ch_payload = buffer_graphql(api_key, ch_query, variables={"organizationId": oid})
    ch_data = ch_payload.get("data") or {}
    channels = ch_data.get("channels")
    if not isinstance(channels, list):
        return []
    return [c for c in channels if isinstance(c, dict)]


def buffer_verify_channel_accessible(
    api_key: str,
    channel_id: str,
    *,
    organization_id: str | None = None,
) -> None:
    """
    Ensure ``channel_id`` exists in Buffer for this API key (GraphQL; uses quota).

    Prefer resolving org + channel at **account setup** (``scripts/sync_buffer_channels.py``)
    and local config checks in ``TwitterService``; the hourly job only calls
    ``buffer_create_queued_post``.

    If ``organization_id`` is set, only that organization's channels are loaded.
    Otherwise every organization on the account is scanned (many HTTP calls).
    """
    want = (channel_id or "").strip()
    if not want:
        raise BufferAPIError("buffer_channel_id is empty")

    if (organization_id or "").strip():
        oid = organization_id.strip()
        for ch in buffer_list_channels(api_key, oid):
            if str(ch.get("id")) == want:
                return
        raise BufferAPIError(
            f"Buffer channel_id={want!r} not found for organization_id={oid!r}"
        )

    org_query = """query {
  account {
    organizations {
      id
      name
    }
  }
}"""
    payload = buffer_graphql(api_key, org_query)
    data = payload.get("data") or {}
    account = data.get("account")
    if not isinstance(account, dict):
        raise BufferAPIError(f"Unexpected account query payload: {data!r}")
    orgs = account.get("organizations")
    if not isinstance(orgs, list) or not orgs:
        raise BufferAPIError("Buffer account has no organizations")

    ch_query = """query GetChannels($organizationId: OrganizationId!) {
  channels(input: { organizationId: $organizationId }) {
    id
    name
    service
  }
}"""

    for org in orgs:
        if not isinstance(org, dict):
            continue
        oid = org.get("id")
        if not oid:
            continue
        ch_payload = buffer_graphql(
            api_key,
            ch_query,
            variables={"organizationId": oid},
        )
        ch_data = ch_payload.get("data") or {}
        channels = ch_data.get("channels")
        if not isinstance(channels, list):
            continue
        for ch in channels:
            if isinstance(ch, dict) and str(ch.get("id")) == want:
                return

    raise BufferAPIError(
        f"Buffer channel_id={want!r} not found under any organization for this API key"
    )

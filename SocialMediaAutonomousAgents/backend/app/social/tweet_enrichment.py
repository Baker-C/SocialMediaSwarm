"""Extract native media and embed-capable URLs from X tweet + includes payloads."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from app.models.tweet_media import TweetMediaEnrichment, TweetMediaItem, TweetUrlEntity

_MEDIA_PRIORITY = ("video", "animated_gif", "photo")
_TWIMG_HOSTS = frozenset({"pbs.twimg.com", "video.twimg.com", "ton.twimg.com"})
_X_HOSTS = frozenset({"twitter.com", "www.twitter.com", "x.com", "www.x.com", "mobile.twitter.com", "mobile.x.com"})


_TEXT_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


def tweet_permalink(tweet_id: str) -> str | None:
    tid = str(tweet_id or "").strip()
    if tid.isdigit():
        return f"https://x.com/i/status/{tid}"
    return None


def _as_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    data = getattr(obj, "data", None)
    if isinstance(data, dict):
        return data
    out: dict[str, Any] = {}
    for key in ("attachments", "entities", "id", "text"):
        val = getattr(obj, key, None)
        if val is not None:
            out[key] = val
    return out


def _includes_media_map(includes: Any) -> dict[str, dict[str, Any]]:
    if includes is None:
        return {}
    media_list = includes.get("media") if isinstance(includes, dict) else getattr(includes, "media", None)
    if not media_list:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in media_list:
        if item is None:
            continue
        row = _as_dict(item)
        key = str(row.get("media_key") or getattr(item, "media_key", "") or "").strip()
        if key:
            out[key] = row
    return out


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _is_twimg_cdn(url: str) -> bool:
    return _host(url) in _TWIMG_HOSTS


def _is_x_status_url(url: str) -> bool:
    host = _host(url)
    if host not in _X_HOSTS:
        return False
    path = (urlparse(url).path or "").lower()
    return "/status/" in path or path.startswith("/i/status/")


def _embed_candidate_url(url: str) -> bool:
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return False
    if _is_twimg_cdn(u):
        return False
    host = _host(u)
    if host in _TWIMG_HOSTS:
        return False
    if host in _X_HOSTS and _is_x_status_url(u):
        return False
    return True


def _parse_url_entities(entities: Any) -> list[TweetUrlEntity]:
    if not entities:
        return []
    urls = entities.get("urls") if isinstance(entities, dict) else getattr(entities, "urls", None)
    if not urls:
        return []
    out: list[TweetUrlEntity] = []
    for item in urls:
        if item is None:
            continue
        row = _as_dict(item)
        ent = TweetUrlEntity(
            url=row.get("url"),
            expanded_url=row.get("expanded_url") or row.get("unwound_url"),
            display_url=row.get("display_url"),
        )
        if ent.url or ent.expanded_url:
            out.append(ent)
    return out


def _primary_media_type(types: list[str]) -> str | None:
    for preferred in _MEDIA_PRIORITY:
        if preferred in types:
            return preferred
    return types[0] if types else None


def enrich_tweet(
    tweet: Any,
    includes: Any = None,
    *,
    tweet_id: str | None = None,
) -> TweetMediaEnrichment:
    """Build media + embed URL enrichment from a Tweepy tweet object and optional includes."""
    td = _as_dict(tweet)
    tid = str(tweet_id or td.get("id") or getattr(tweet, "id", "") or "").strip()

    media_by_key = _includes_media_map(includes)
    attachments = td.get("attachments") or getattr(tweet, "attachments", None)
    media_keys: list[str] = []
    if attachments:
        keys = attachments.get("media_keys") if isinstance(attachments, dict) else getattr(attachments, "media_keys", None)
        if keys:
            media_keys = [str(k) for k in keys if k]

    media_items: list[TweetMediaItem] = []
    types_seen: list[str] = []
    for mk in media_keys:
        raw = media_by_key.get(mk, {})
        mtype = str(raw.get("type") or "").strip().lower()
        if mtype and mtype not in types_seen:
            types_seen.append(mtype)
        media_items.append(
            TweetMediaItem(
                media_key=mk,
                type=mtype,
                url=raw.get("url"),
                preview_image_url=raw.get("preview_image_url"),
            )
        )

    url_entities = _parse_url_entities(td.get("entities") or getattr(tweet, "entities", None))

    embed_urls: list[str] = []
    permalink = tweet_permalink(tid)
    if permalink:
        embed_urls.append(permalink)

    for ent in url_entities:
        candidate = (ent.expanded_url or ent.url or "").strip()
        if not candidate or not _embed_candidate_url(candidate):
            continue
        if candidate not in embed_urls:
            embed_urls.append(candidate)

    return TweetMediaEnrichment(
        tweet_permalink=permalink,
        media_types=types_seen,
        primary_media_type=_primary_media_type(types_seen),
        media=media_items,
        embed_urls=embed_urls,
        url_entities=url_entities,
    )


def enrichment_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Parse enrichment fields from a reference row or PostData model_dump."""
    media_types = row.get("media_types")
    embed_urls = row.get("embed_urls")
    media_raw = row.get("media")
    media: list[TweetMediaItem] = []
    if isinstance(media_raw, list):
        for item in media_raw:
            if isinstance(item, TweetMediaItem):
                media.append(item)
            elif isinstance(item, dict):
                try:
                    media.append(TweetMediaItem.model_validate(item))
                except Exception:
                    continue
    url_raw = row.get("url_entities")
    url_entities: list[TweetUrlEntity] = []
    if isinstance(url_raw, list):
        for item in url_raw:
            if isinstance(item, TweetUrlEntity):
                url_entities.append(item)
            elif isinstance(item, dict):
                try:
                    url_entities.append(TweetUrlEntity.model_validate(item))
                except Exception:
                    continue
    return {
        "tweet_permalink": row.get("tweet_permalink"),
        "primary_media_type": row.get("primary_media_type"),
        "media_types": list(media_types) if isinstance(media_types, list) else [],
        "media": media,
        "embed_urls": [str(u) for u in embed_urls if u] if isinstance(embed_urls, list) else [],
        "url_entities": url_entities,
    }


def enrichment_to_row_dict(enrichment: TweetMediaEnrichment) -> dict[str, Any]:
    return {
        "tweet_permalink": enrichment.tweet_permalink,
        "media_types": list(enrichment.media_types),
        "primary_media_type": enrichment.primary_media_type,
        "media": [m.model_dump(exclude_none=True) for m in enrichment.media],
        "embed_urls": list(enrichment.embed_urls),
        "url_entities": [u.model_dump(exclude_none=True) for u in enrichment.url_entities],
    }


def apply_enrichment_to_post_data(post: Any, enrichment: TweetMediaEnrichment) -> None:
    """Mutate a PostData instance with enrichment fields."""
    post.tweet_permalink = enrichment.tweet_permalink
    post.media_types = list(enrichment.media_types)
    post.primary_media_type = enrichment.primary_media_type
    post.media = list(enrichment.media)
    post.embed_urls = list(enrichment.embed_urls)
    post.url_entities = list(enrichment.url_entities)


def _media_item_direct_url(item: Any) -> str | None:
    """Direct URL for a native X attachment (photo, video, GIF)."""
    if isinstance(item, dict):
        mtype = str(item.get("type") or "").strip().lower()
        url = str(item.get("url") or "").strip()
        preview = str(item.get("preview_image_url") or "").strip()
    else:
        mtype = str(getattr(item, "type", "") or "").strip().lower()
        url = str(getattr(item, "url", None) or "").strip()
        preview = str(getattr(item, "preview_image_url", None) or "").strip()

    def ok(u: str) -> bool:
        return bool(u) and u.startswith(("http://", "https://"))

    if mtype in ("video", "animated_gif"):
        if ok(url):
            return url
        if ok(preview):
            return preview
    if mtype == "photo":
        if ok(url):
            return url
        if ok(preview):
            return preview
    if ok(url):
        return url
    if ok(preview):
        return preview
    return None


def row_has_native_media_url(row: dict[str, Any]) -> bool:
    """True when the row has at least one native attachment with a fetchable URL."""
    if not isinstance(row, dict):
        return False
    for item in row.get("media") or []:
        if _media_item_direct_url(item):
            return True
    return False


def row_has_url(row: dict[str, Any]) -> bool:
    """True when the tweet has a link suitable for reference-pool inclusion."""
    if row_has_native_media_url(row):
        return True
    text = str(row.get("text") or "")
    if _TEXT_URL_RE.search(text):
        return True
    url_entities = row.get("url_entities")
    if isinstance(url_entities, list) and len(url_entities) > 0:
        return True
    embed_urls = row.get("embed_urls")
    if isinstance(embed_urls, list):
        permalink = str(row.get("tweet_permalink") or "").strip()
        for raw in embed_urls:
            u = str(raw or "").strip()
            if not u:
                continue
            if u == permalink:
                continue
            if _embed_candidate_url(u):
                return True
    return False


def filter_rows_with_urls(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only reference rows that contain at least one URL (entities, external embed, or text link)."""
    return [r for r in rows if isinstance(r, dict) and row_has_url(r)]


def select_chosen_post_embed_url(row: dict[str, Any]) -> str | None:
    """
    Permalink for the chosen reference tweet (X status card unfurl).

    Used when the appended URL must match the same post as the rewrite/quote source,
    not an external link contained in that tweet.
    """
    if not isinstance(row, dict):
        return None
    tid = str(row.get("id") or row.get("tweet_id") or "").strip()
    if not tid.isdigit():
        return None
    permalink = str(row.get("tweet_permalink") or "").strip()
    if permalink and _is_x_status_url(permalink):
        return permalink
    return tweet_permalink(tid)


def select_chosen_post_media_url(row: dict[str, Any]) -> str | None:
    """
    URL to append for a rich preview on X (link card or embedded tweet).

    X unfurls external article URLs and ``x.com/i/status/…`` permalinks as cards.
    Raw ``pbs.twimg.com`` / ``video.twimg.com`` CDN links stay plain hyperlinks,
    so they are never returned here.
    """
    if not isinstance(row, dict):
        return None

    for ent in row.get("url_entities") or []:
        if isinstance(ent, dict):
            candidate = str(ent.get("expanded_url") or ent.get("url") or "").strip()
        else:
            candidate = str(getattr(ent, "expanded_url", None) or getattr(ent, "url", None) or "").strip()
        if candidate and _embed_candidate_url(candidate):
            return candidate

    text = str(row.get("text") or "")
    for match in _TEXT_URL_RE.findall(text):
        candidate = match.strip().rstrip(".,;)")
        if candidate and _embed_candidate_url(candidate):
            return candidate

    permalink = str(row.get("tweet_permalink") or "").strip()
    for raw in row.get("embed_urls") or []:
        u = str(raw or "").strip()
        if not u or u == permalink:
            continue
        if _embed_candidate_url(u):
            return u

    # Photo/video-only posts: tweet permalink embeds the source post (with its media).
    if row_has_native_media_url(row):
        return select_chosen_post_embed_url(row)

    return select_chosen_post_embed_url(row)


def select_post_append_url(row: dict[str, Any]) -> str | None:
    """
    Pick one URL to append to a post body for X link preview / tweet card unfurl.

    Prefers expanded external links, then the source tweet permalink.
    """
    if not isinstance(row, dict):
        return None
    for ent in row.get("url_entities") or []:
        if isinstance(ent, dict):
            candidate = str(ent.get("expanded_url") or ent.get("url") or "").strip()
        else:
            candidate = str(getattr(ent, "expanded_url", None) or getattr(ent, "url", None) or "").strip()
        if candidate and _embed_candidate_url(candidate):
            return candidate
    permalink = str(row.get("tweet_permalink") or "").strip()
    for raw in row.get("embed_urls") or []:
        u = str(raw or "").strip()
        if not u or u == permalink:
            continue
        if _embed_candidate_url(u):
            return u
    tid = str(row.get("id") or row.get("tweet_id") or "").strip()
    return permalink or tweet_permalink(tid)


def append_url_to_post_body(body: str, url: str | None, *, max_len: int = 280) -> str:
    """Append a bare URL to the end of post text when it fits within X length limits."""
    text = (body or "").strip()
    link = (url or "").strip()
    if not link:
        return text
    for sep in ("\n\n", "\n", " "):
        candidate = f"{text}{sep}{link}" if text else link
        if len(candidate) <= max_len:
            return candidate
    return text

"""Print Buffer organizations via GraphQL (same request as the Buffer docs curl example)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx

from app.core.config import settings

QUERY = """query GetOrganizations {
  account {
    organizations {
      id
      name
    }
  }
}"""


def main() -> int:
    key = (settings.buffer_api_key or "").strip()
    if not key:
        print("Set BUFFER_API_KEY in backend/.env", file=sys.stderr)
        return 1
    r = httpx.post(
        "https://api.buffer.com",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={"query": QUERY},
        timeout=60.0,
    )
    print(r.status_code)
    try:
        print(json.dumps(r.json(), indent=2))
    except Exception:
        print(r.text)
    return 0 if r.is_success else 1


if __name__ == "__main__":
    raise SystemExit(main())

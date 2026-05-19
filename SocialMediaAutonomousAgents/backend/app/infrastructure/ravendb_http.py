"""Minimal RavenDB HTTP client (sync) for document CRUD and ad-hoc RQL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings


class RavenDBHttpError(RuntimeError):
    pass


def _ravendb_cert_dir() -> Path:
    """Convention: ``~/ravendb/certs`` (e.g. ``C:\\Users\\cdbak\\ravendb\\certs``)."""
    return Path.home() / "ravendb" / "certs"


def discover_ravendb_client_cert_paths(cert_dir: Path) -> tuple[str | None, str | None]:
    """
    Pick PEM paths under ``cert_dir`` when env vars are unset.

    Tries, in order:

    1. ``client.pem`` + ``client.key``
    2. ``client.pem`` alone (combined cert + key)
    3. ``client.crt`` + ``client.key``
    4. Any other ``*.crt`` with a sibling ``*.key`` of the same basename (e.g.
       ``ravendb-foo.instance.crt`` + ``ravendb-foo.instance.key``), lexicographically first.
    """
    if not cert_dir.is_dir():
        return None, None
    pem = cert_dir / "client.pem"
    key = cert_dir / "client.key"
    crt = cert_dir / "client.crt"
    if pem.is_file() and key.is_file():
        return str(pem), str(key)
    if pem.is_file():
        return str(pem), None
    if crt.is_file() and key.is_file():
        return str(crt), str(key)
    for crt_path in sorted(cert_dir.glob("*.crt")):
        key_path = crt_path.with_suffix(".key")
        if key_path.is_file():
            return str(crt_path), str(key_path)
    return None, None


class RavenDBHttpClient:
    def __init__(
        self,
        base_url: str | None = None,
        database: str | None = None,
        verify_ssl: bool | None = None,
    ) -> None:
        self.base_url = (base_url or settings.ravendb_url).rstrip("/")
        self.database = database or settings.ravendb_db
        self.verify_ssl = settings.ravendb_verify_ssl if verify_ssl is None else verify_ssl
        self._client: httpx.Client | None = None

    def _client_cert(self) -> str | tuple[str, str] | None:
        cert = (settings.ravendb_client_cert or "").strip()
        key = (settings.ravendb_client_key or "").strip()
        if not cert:
            dc, dk = discover_ravendb_client_cert_paths(_ravendb_cert_dir())
            if dc:
                cert = dc
                if not key and dk:
                    key = dk
        if not cert:
            return None
        if key:
            return (cert, key)
        return cert

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                verify=self.verify_ssl,
                cert=self._client_cert(),
                timeout=60.0,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def _docs_url(self, doc_id: str) -> str:
        encoded = quote(doc_id, safe="")
        return f"{self.base_url}/databases/{self.database}/docs?id={encoded}"

    def _queries_url(self) -> str:
        return f"{self.base_url}/databases/{self.database}/queries"

    def put_document(self, doc_id: str, document: dict[str, Any], *, collection: str | None = None) -> None:
        payload = dict(document)
        meta = payload.setdefault("@metadata", {})
        meta.setdefault("@collection", collection or "Accounts")
        meta.setdefault("@id", doc_id)
        r = self.client.put(self._docs_url(doc_id), content=json.dumps(payload))
        if r.status_code >= 400:
            raise RavenDBHttpError(f"PUT {doc_id} failed: {r.status_code} {r.text}")

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        r = self.client.get(self._docs_url(doc_id))
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise RavenDBHttpError(f"GET {doc_id} failed: {r.status_code} {r.text}")
        data = r.json()
        # Some server/proxy responses wrap a single document as {"Results":[{...}], "Includes":{}}.
        if isinstance(data, dict) and isinstance(data.get("Results"), list):
            results = data["Results"]
            if len(results) == 0:
                return None
            if len(results) == 1 and isinstance(results[0], dict):
                return results[0]
        return data if isinstance(data, dict) else None

    def delete_document(self, doc_id: str, change_vector: str | None = None) -> bool:
        url = self._docs_url(doc_id)
        if change_vector:
            url = f"{url}&changeVector={quote(change_vector, safe='')}"
        r = self.client.delete(url)
        if r.status_code == 404:
            return False
        if r.status_code >= 400:
            raise RavenDBHttpError(f"DELETE {doc_id} failed: {r.status_code} {r.text}")
        return True

    def query(self, rql: str) -> list[dict[str, Any]]:
        body = {"Query": rql}
        r = self.client.post(self._queries_url(), json=body)
        if r.status_code >= 400:
            raise RavenDBHttpError(f"Query failed: {r.status_code} {r.text}")
        data = r.json()
        results = data.get("Results") or data.get("results") or []
        if not isinstance(results, list):
            return []
        out: list[dict[str, Any]] = []
        for item in results:
            if isinstance(item, dict):
                out.append(item)
        return out


_client: RavenDBHttpClient | None = None


def get_ravendb_client() -> RavenDBHttpClient:
    global _client
    if _client is None:
        _client = RavenDBHttpClient()
    return _client

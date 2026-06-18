"""The testability seam: ``BrowserPort`` protocol + real ``PlaywrightBrowser`` impl.

CRITICAL: Playwright is imported LAZILY inside ``PlaywrightBrowser.__init__`` so this
module (and everything that depends only on the protocol) imports without Playwright
installed. The detector / handlers / orchestrator depend ONLY on ``BrowserPort``.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BrowserPort(Protocol):
    """Minimal protocol over the Playwright operations the handlers use."""

    def goto(self, url: str) -> None: ...
    def url(self) -> str: ...
    def exists(self, selector: str) -> bool: ...
    def text(self, selector: str) -> str: ...  # "" if absent
    def fill(self, selector: str, value: str) -> None: ...
    def click(self, selector: str) -> None: ...
    def upload(self, selector: str, data: bytes, filename: str) -> None: ...
    def wait_for(self, selector: str, timeout_ms: int = 15000) -> bool: ...
    def storage_state(self) -> str: ...  # JSON cookies/localStorage -> session_cookies


class PlaywrightBrowser:
    """Wraps a persistent-context real Chrome. Stealth patches applied here only.

    Playwright is imported lazily so importing this module never requires it.
    """

    def __init__(self, profile_dir: str, *, headless: bool = False) -> None:
        # Lazy import: keeps the package importable without playwright installed.
        from playwright.sync_api import sync_playwright  # noqa: PLC0415

        self._pw = sync_playwright().start()
        # channel="chrome" => the operator's installed Chrome (best fingerprint).
        self._context = self._pw.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=headless,
            channel="chrome",
        )
        # Apply playwright-stealth / rebrowser patches HERE only, if available.
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()

    # ---- BrowserPort ----
    def goto(self, url: str) -> None:
        self._page.goto(url)

    def url(self) -> str:
        return self._page.url

    def exists(self, selector: str) -> bool:
        return self._page.locator(selector).count() > 0

    def text(self, selector: str) -> str:
        loc = self._page.locator(selector)
        if loc.count() == 0:
            return ""
        return loc.first.inner_text()

    def fill(self, selector: str, value: str) -> None:
        self._page.locator(selector).first.fill(value)

    def click(self, selector: str) -> None:
        self._page.locator(selector).first.click()

    def upload(self, selector: str, data: bytes, filename: str) -> None:
        self._page.locator(selector).first.set_input_files(
            files=[{"name": filename, "mimeType": "image/png", "buffer": data}]
        )

    def wait_for(self, selector: str, timeout_ms: int = 15000) -> bool:
        try:
            self._page.locator(selector).first.wait_for(timeout=timeout_ms)
            return True
        except Exception:
            return False

    def storage_state(self) -> str:
        import json  # noqa: PLC0415

        return json.dumps(self._context.storage_state())

    def close(self) -> None:
        try:
            self._context.close()
        finally:
            self._pw.stop()

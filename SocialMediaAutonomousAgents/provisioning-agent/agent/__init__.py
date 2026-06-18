"""Local provisioning agent (Playwright + real Chrome).

All decision logic depends only on :class:`agent.browser_port.BrowserPort`, so it is
unit-testable without a real browser. Playwright is imported lazily, never at module
import time outside :class:`agent.browser_port.PlaywrightBrowser`.
"""

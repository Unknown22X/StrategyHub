"""Localhost-only launcher for the RangeBot web control panel."""

from __future__ import annotations

import argparse
import sys
import time
from urllib.parse import urlparse
import webbrowser

import httpx

from rangebot.ui.engine_bootstrap import start_bundled_engine_if_needed


_ALLOWED_ENGINE_HOSTS = {"127.0.0.1", "localhost", "::1"}


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open the RangeBot control panel.")
    parser.add_argument("--engine-url", default="http://127.0.0.1:8765")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Verify engine connectivity once and exit without opening a browser.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Wait for the engine and print the dashboard URL without opening it.",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=45.0,
        help="Seconds to wait for the localhost engine.",
    )
    parsed = parser.parse_args(arguments)
    parsed.engine_url = _validated_engine_url(parser, parsed.engine_url)
    if parsed.startup_timeout <= 0:
        parser.error("--startup-timeout must be greater than zero.")
    return parsed


def _validated_engine_url(parser: argparse.ArgumentParser, value: str) -> str:
    normalized = value.rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "http" or parsed.hostname not in _ALLOWED_ENGINE_HOSTS:
        parser.error("--engine-url must use HTTP on localhost.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("--engine-url must be a plain localhost origin.")
    return normalized


def _wait_for_engine(engine_url: str, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{engine_url}/health", timeout=0.5)
            if response.is_success:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    return False


def _dashboard_is_available(engine_url: str) -> bool:
    try:
        response = httpx.get(f"{engine_url}/app/", timeout=2.0)
    except httpx.HTTPError:
        return False
    return response.is_success and "text/html" in response.headers.get("content-type", "")


def main(arguments: list[str] | None = None) -> None:
    parsed = parse_arguments(arguments)
    start_bundled_engine_if_needed()

    if not _wait_for_engine(parsed.engine_url, parsed.startup_timeout):
        print(
            f"RangeBot engine did not become available at {parsed.engine_url}.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if parsed.once:
        raise SystemExit(0)

    dashboard_url = f"{parsed.engine_url}/app/"
    if not _dashboard_is_available(parsed.engine_url):
        print(
            "The RangeBot engine is running, but compiled dashboard assets are unavailable. "
            "Build frontend/dist before packaging or use the Vite development server.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    if parsed.no_browser:
        print(dashboard_url)
        raise SystemExit(0)

    if not webbrowser.open(dashboard_url, new=2):
        print(dashboard_url)


if __name__ == "__main__":
    main()

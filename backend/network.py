"""Bounded, cancellable article fetching, shared by discovery and enrichment."""
from contextlib import contextmanager
from contextvars import ContextVar
from ipaddress import ip_address
import socket
import time
from urllib.parse import urlsplit, urljoin
import requests
from bs4 import BeautifulSoup

_context = ContextVar("scan_network", default=None)


@contextmanager
def fetch_context(timeout=20, cancel=None, budget=150):
    token = _context.set({"timeout": timeout, "cancel": cancel, "deadline": time.monotonic() + budget, "cache": {}})
    try:
        yield
    finally:
        _context.reset(token)


def validate_url(url):
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError("Enter a valid public article URL.")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Article URLs must use HTTP or HTTPS without credentials.")
    if parsed.port not in (None, 80, 443):
        raise ValueError("Only standard web ports are supported.")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError("Article URLs must resolve to public internet addresses.")
    return url


def check():
    ctx = _context.get()
    if ctx and ctx["cancel"] and ctx["cancel"]():
        raise InterruptedError("Run cancelled by user")
    if ctx and time.monotonic() >= ctx["deadline"]:
        raise TimeoutError("This source exceeded its time budget.")
    return ctx


def get_soup(url, timeout=None):
    ctx = check()
    if ctx and url in ctx["cache"]:
        return BeautifulSoup(ctx["cache"][url], "html.parser")
    original = url
    for _ in range(6):
        ctx = check()
        validate_url(url)
        seconds = timeout or (ctx["timeout"] if ctx else 20)
        if ctx:
            seconds = max(.1, min(seconds, ctx["deadline"] - time.monotonic()))
        with requests.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; GTAIntelligence/7.0)", "Accept-Language": "en-US,en;q=0.9"}, timeout=seconds, allow_redirects=False, stream=True) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers["Location"])
                continue
            response.raise_for_status()
            chunks, length = [], 0
            for chunk in response.iter_content(65536):
                check()
                length += len(chunk)
                if length > 6 * 1024 * 1024:
                    raise ValueError("Source article exceeds the 6 MB download limit.")
                chunks.append(chunk)
            html = b"".join(chunks)
        if ctx:
            ctx["cache"][original] = html
        return BeautifulSoup(html, "html.parser")
    raise ValueError("Too many article redirects.")

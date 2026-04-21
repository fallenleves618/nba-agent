from __future__ import annotations

import gzip
import json
import socket
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip",
    "Connection": "close",
}


def fetch_text(
    url: str,
    *,
    timeout: float = 12.0,
    headers: Optional[dict[str, str]] = None,
) -> str:
    request_headers = dict(DEFAULT_HEADERS)
    if headers:
        request_headers.update(headers)

    request = Request(url, headers=request_headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
            if response.headers.get("Content-Encoding", "").lower() == "gzip":
                payload = gzip.decompress(payload)

            charset = response.headers.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="ignore")
    except (HTTPError, URLError, TimeoutError, socket.timeout, OSError):
        return ""


def post_json(
    url: str,
    payload: dict[str, object],
    *,
    timeout: float = 12.0,
    headers: Optional[dict[str, str]] = None,
) -> tuple[bool, str]:
    request_headers = {
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json; charset=utf-8",
        "Connection": "close",
    }
    if headers:
        request_headers.update(headers)

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers=request_headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            payload_bytes = response.read()
            if response.headers.get("Content-Encoding", "").lower() == "gzip":
                payload_bytes = gzip.decompress(payload_bytes)

            charset = response.headers.get_content_charset() or "utf-8"
            return True, payload_bytes.decode(charset, errors="ignore")
    except HTTPError as exc:
        try:
            payload_bytes = exc.read()
            charset = exc.headers.get_content_charset() or "utf-8"
            return False, payload_bytes.decode(charset, errors="ignore")
        except Exception:
            return False, str(exc)
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        return False, str(exc)

from __future__ import annotations

import re
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin

from nba_agent.models import CollectedItem


_PC_POST_RE = re.compile(r"^https?://bbs\.hupu\.com/\d+(?:-\d+)?\.html(?:#.*)?$")
_MOBILE_POST_RE = re.compile(r"^https?://m\.hupu\.com/bbs/\d+(?:\?.*)?$")
_ABS_POST_ID_RE = re.compile(r"(\d+)")
_META_DESCRIPTION_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_DATETIME_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_MAIN_THREAD_RE = re.compile(
    r'<div class="thread-content-detail">\s*(.*?)\s*</div><div class="seo-dom">',
    re.DOTALL,
)
_AUTHOR_RE = re.compile(
    r'post-user-comp-info-top-name[^"]*"[^>]*>([^<]+)</a>', re.IGNORECASE
)
_TITLE_RE = re.compile(r"<h1[^>]*>(.*?)<!-- -->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_IMAGE_BLOCK_RE = re.compile(r"<div data-hupu-node=\"image\">.*?</div>", re.DOTALL)
_IMAGE_RE = re.compile(r"<img[^>]*>", re.IGNORECASE)
_BR_RE = re.compile(r"</?(?:br|p|span|div)[^>]*>", re.IGNORECASE)


def _clean_text(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_post_href(href: str) -> bool:
    return bool(_PC_POST_RE.match(href) or _MOBILE_POST_RE.match(href))


def _canonical_pc_url(href: str) -> str:
    if _PC_POST_RE.match(href):
        return href.split("#", 1)[0]

    match = _ABS_POST_ID_RE.search(href)
    if not match:
        return href
    return f"https://bbs.hupu.com/{match.group(1)}.html"


class HupuLinkParser(HTMLParser):
    def __init__(self, source: str, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.base_url = base_url
        self._current_href: Optional[str] = None
        self._current_parts: list[str] = []
        self._items: list[CollectedItem] = []

    @property
    def items(self) -> list[CollectedItem]:
        return self._items

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag != "a":
            return

        attr_map = dict(attrs)
        href = attr_map.get("href")
        if not href:
            return
        href = urljoin(self.base_url, href)
        if not _is_post_href(href):
            return

        self._current_href = href
        self._current_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href is None:
            return
        text = _clean_text(data)
        if text:
            self._current_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._current_href is None:
            return

        title = _pick_title(self._current_parts)
        if title:
            self._items.append(
                CollectedItem(
                    source=self.source,
                    title=title,
                    url=_canonical_pc_url(self._current_href),
                )
            )

        self._current_href = None
        self._current_parts = []


def _pick_title(parts: list[str]) -> str:
    skip_text = {
        "下一页",
        "上一页",
        "...",
        "高级回复",
        "查看评论",
        "只看此人",
        "举报",
        "回复",
        "社区首页",
        "篮球资讯",
        "NBA",
    }
    for part in parts:
        candidate = _clean_text(part)
        if not candidate:
            continue
        if candidate in skip_text:
            continue
        if candidate.isdigit():
            continue
        if len(candidate) < 6:
            continue
        if re.fullmatch(r"[\d /:+\-]+", candidate):
            continue
        if candidate.endswith("回复") and re.search(r"\d", candidate):
            continue
        return candidate
    return ""


def parse_list_page(html: str, *, source: str, base_url: str) -> list[CollectedItem]:
    parser = HupuLinkParser(source=source, base_url=base_url)
    parser.feed(html)

    deduped: list[CollectedItem] = []
    seen: set[tuple[str, str]] = set()
    for item in parser.items:
        key = (item.title, item.url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def parse_detail_page(html: str) -> dict[str, object]:
    if not html:
        return {}

    description_match = _META_DESCRIPTION_RE.search(html)
    description = _clean_text(description_match.group(1)) if description_match else ""
    content_text = _extract_main_thread_text(html) or description
    author_match = _AUTHOR_RE.search(html)
    author = _clean_text(author_match.group(1)) if author_match else ""
    title_match = _TITLE_RE.search(html)
    title = _clean_text(_strip_tags(title_match.group(1))) if title_match else ""

    publish_time = None
    datetime_match = _DATETIME_RE.search(html)
    if datetime_match:
        try:
            publish_time = datetime.strptime(datetime_match.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            publish_time = None

    return {
        "content_excerpt": content_text,
        "publish_time": publish_time,
        "author": author,
        "title": title,
    }


def _extract_main_thread_text(html: str) -> str:
    match = _MAIN_THREAD_RE.search(html)
    if not match:
        return ""

    fragment = match.group(1)
    fragment = _IMAGE_BLOCK_RE.sub(" ", fragment)
    fragment = _IMAGE_RE.sub(" ", fragment)
    fragment = _BR_RE.sub("\n", fragment)
    text = _strip_tags(fragment)
    lines = [_clean_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def _strip_tags(fragment: str) -> str:
    return _TAG_RE.sub(" ", fragment)

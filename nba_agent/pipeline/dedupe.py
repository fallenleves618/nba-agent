from __future__ import annotations

import re

from nba_agent.models import CollectedItem


def _normalize_title(title: str) -> str:
    title = title.lower().strip()
    title = re.sub(r"\s+", "", title)
    title = re.sub(r"[^\w\u4e00-\u9fff]+", "", title)
    return title


def dedupe_items(items: list[CollectedItem]) -> list[CollectedItem]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    deduped: list[CollectedItem] = []

    for item in items:
        canonical_url = item.url.split("#", 1)[0]
        normalized_title = _normalize_title(item.title)
        if canonical_url in seen_urls or normalized_title in seen_titles:
            continue

        seen_urls.add(canonical_url)
        seen_titles.add(normalized_title)
        deduped.append(item)

    return deduped

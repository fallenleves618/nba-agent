from __future__ import annotations

import json
import re
from urllib.parse import quote


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_PUNCT_RE = re.compile(r"[-_\s]")


def parse_suggestion_response(payload: str) -> list[dict[str, object]]:
    if not payload:
        return []

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []

    forums: list[dict[str, object]] = []
    seen: set[int | str] = set()
    for section_key in ("query_match", "query_tag"):
        section = data.get(section_key)
        if not isinstance(section, dict):
            continue
        search_data = section.get("search_data")
        if not isinstance(search_data, list):
            continue

        for entry in search_data:
            if not isinstance(entry, dict):
                continue
            forum_name = str(entry.get("fname", "")).strip()
            if not forum_name:
                continue

            forum_id = entry.get("forum_id") or forum_name
            if forum_id in seen:
                continue
            seen.add(forum_id)
            forums.append(entry)

    return forums


def canonical_forum_url(forum_name: str) -> str:
    return f"https://tieba.baidu.com/f?kw={quote(forum_name)}"


def normalize_query(text: str) -> str:
    return _PUNCT_RE.sub("", text).strip()


def contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))

from __future__ import annotations


SOURCE_PRIORITY = {
    "official": 100,
    "hupu": 60,
    "tieba": 20,
    "demo": 10,
}


def source_priority(source: str) -> int:
    return SOURCE_PRIORITY.get(source, 0)

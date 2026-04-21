from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import quote

from nba_agent.collectors.base import BaseCollector
from nba_agent.collectors.tieba_parser import (
    canonical_forum_url,
    contains_cjk,
    normalize_query,
    parse_suggestion_response,
)
from nba_agent.http import fetch_text
from nba_agent.models import CollectedItem, KeywordRules, KeywordTerm, TiebaSettings
from nba_agent.pipeline.keywords import matched_term_names, seed_terms, should_keep_text

try:
    import aiotieba
except ImportError:  # pragma: no cover - optional dependency in runtime env
    aiotieba = None


class TiebaCollector(BaseCollector):
    name = "tieba"
    base_suggestion_url = "https://tieba.baidu.com/suggestion?ie=utf-8&query={query}"

    def __init__(self, settings: TiebaSettings) -> None:
        self.settings = settings

    def collect(self, rules: KeywordRules) -> list[CollectedItem]:
        items: list[CollectedItem] = []
        seen_urls: set[str] = set()
        forums_for_threads: list[dict[str, object]] = []

        for query in self._query_terms(rules):
            payload = fetch_text(
                self.base_suggestion_url.format(query=query["encoded"]),
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://tieba.baidu.com/",
                },
            )
            if not payload:
                continue

            forums = parse_suggestion_response(payload)
            forums = self._select_forums(
                forums,
                query_text=query["query"],
                canonical_name=query["canonical_name"],
            )

            for forum in forums[: self.settings.max_forums_per_query]:
                item = self._build_item(
                    forum,
                    query_text=query["query"],
                    canonical_name=query["canonical_name"],
                )
                if item.url in seen_urls:
                    continue
                haystack = f"{item.title}\n{item.content_excerpt}"
                if not should_keep_text(haystack, rules):
                    continue
                seen_urls.add(item.url)
                items.append(item)
                forums_for_threads.append(
                    {
                        "forum_name": str(forum.get("fname", "")).strip(),
                        "forum_id": int(forum.get("forum_id", 0) or 0),
                        "query_text": query["query"],
                        "canonical_name": query["canonical_name"],
                    }
                )

        if self.settings.experimental_thread_fetch_enabled:
            thread_items = self._collect_experimental_threads(forums_for_threads, rules)
            for item in thread_items:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                items.append(item)

        return items

    def _query_terms(self, rules: KeywordRules) -> list[dict[str, str]]:
        if not rules.terms:
            return [
                {
                    "query": keyword,
                    "encoded": quote(keyword),
                    "canonical_name": keyword,
                }
                for keyword in seed_terms(rules)
                if keyword
            ]

        queries: list[dict[str, str]] = []
        seen: set[str] = set()
        for term in rules.terms:
            if term.category not in self.settings.query_categories:
                continue
            for query_text in self._preferred_queries(term):
                normalized = normalize_query(query_text)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                queries.append(
                    {
                        "query": query_text,
                        "encoded": quote(query_text),
                        "canonical_name": term.name,
                    }
                )
        return queries

    def _preferred_queries(self, term: KeywordTerm) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        def add(candidate: str) -> None:
            normalized = normalize_query(candidate)
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            candidates.append(normalized)

        add(term.name)
        for alias in term.aliases:
            add(alias)
        for alias in term.weak_aliases:
            add(alias)

        chinese_candidates = [text for text in candidates if contains_cjk(text)]
        chinese_candidates.sort(key=lambda text: (0 if 2 <= len(text) <= 4 else 1, len(text)))
        latin_candidates = [text for text in candidates if not contains_cjk(text)]
        return (chinese_candidates + latin_candidates)[:2]

    def _select_forums(
        self,
        forums: list[dict[str, object]],
        *,
        query_text: str,
        canonical_name: str,
    ) -> list[dict[str, object]]:
        normalized_query = normalize_query(query_text).lower()
        normalized_name = normalize_query(canonical_name).lower()

        def rank_key(forum: dict[str, object]) -> tuple[int, int, int]:
            forum_name = str(forum.get("fname", ""))
            forum_desc = str(forum.get("forum_desc", ""))
            fclass1 = str(forum.get("fclass1", ""))
            fclass2 = str(forum.get("fclass2", ""))
            haystack = (
                f"{forum_name} {forum_desc} {fclass1} {fclass2}".lower()
            )
            normalized_forum_name = normalize_query(forum_name).lower()
            normalized_forum_desc = normalize_query(forum_desc).lower()
            exact_name_hit = int(
                normalized_query in normalized_forum_name
                or normalized_name in normalized_forum_name
                or normalized_query in normalized_forum_desc
                or normalized_name in normalized_forum_desc
            )
            sports_hit = int(
                any(token in haystack for token in ("nba", "篮球", "体育", "球迷", "运动员"))
            )
            member_num = int(forum.get("member_num", 0) or 0)
            return (exact_name_hit, sports_hit, member_num)

        ranked = sorted(forums, key=rank_key, reverse=True)
        kept: list[dict[str, object]] = []
        for forum in ranked:
            forum_name = str(forum.get("fname", ""))
            forum_desc = str(forum.get("forum_desc", ""))
            fclass1 = str(forum.get("fclass1", ""))
            fclass2 = str(forum.get("fclass2", ""))
            haystack = (
                f"{forum_name} {forum_desc} {fclass1} {fclass2}".lower()
            )
            normalized_forum_name = normalize_query(forum_name).lower()
            normalized_forum_desc = normalize_query(forum_desc).lower()
            name_or_desc_hit = (
                normalized_query in normalized_forum_name
                or normalized_name in normalized_forum_name
                or normalized_query in normalized_forum_desc
                or normalized_name in normalized_forum_desc
            )
            sports_hit = any(
                token in haystack for token in ("nba", "篮球", "体育", "球迷", "运动员")
            )
            if not (name_or_desc_hit and sports_hit):
                continue
            kept.append(forum)
        return kept

    def _build_item(
        self,
        forum: dict[str, object],
        *,
        query_text: str,
        canonical_name: str,
    ) -> CollectedItem:
        forum_name = str(forum.get("fname", "")).strip()
        forum_desc = str(forum.get("forum_desc", "")).strip()
        member_num = int(forum.get("member_num", 0) or 0)
        thread_num = int(forum.get("thread_num", 0) or 0)
        fclass1 = str(forum.get("fclass1", "")).strip()
        fclass2 = str(forum.get("fclass2", "")).strip()
        forum_id = str(forum.get("forum_id", "")).strip()

        excerpt_parts = []
        if forum_desc:
            excerpt_parts.append(f"吧简介: {forum_desc}")
        excerpt_parts.append(f"成员 {member_num}，主题 {thread_num}")
        if fclass1 or fclass2:
            excerpt_parts.append(f"分类: {fclass1}/{fclass2}".strip("/"))
        excerpt_parts.append(f"命中贴吧查询词: {query_text}")

        return CollectedItem(
            source=self.name,
            title=f"贴吧社区: {forum_name}吧",
            url=canonical_forum_url(forum_name),
            content_excerpt="；".join(part for part in excerpt_parts if part),
            tags=["community", "tieba", "forum", canonical_name],
            raw_payload=f"forum_id={forum_id}",
        )

    def _collect_experimental_threads(
        self, forums: list[dict[str, object]], rules: KeywordRules
    ) -> list[CollectedItem]:
        if aiotieba is None:
            return []
        if self.settings.experimental_thread_fetch_mode != "ws":
            return []

        unique_forums: list[dict[str, object]] = []
        seen_forum_ids: set[int] = set()
        for forum in forums:
            forum_id = int(forum.get("forum_id", 0) or 0)
            if forum_id <= 0 or forum_id in seen_forum_ids:
                continue
            seen_forum_ids.add(forum_id)
            unique_forums.append(forum)

        unique_forums = unique_forums[: self.settings.max_forums_for_threads]
        if not unique_forums:
            return []

        return asyncio.run(self._collect_experimental_threads_async(unique_forums, rules))

    async def _collect_experimental_threads_async(
        self, forums: list[dict[str, object]], rules: KeywordRules
    ) -> list[CollectedItem]:
        collected: list[CollectedItem] = []
        async with aiotieba.Client(try_ws=True) as client:
            for forum in forums:
                forum_id = int(forum.get("forum_id", 0) or 0)
                forum_name = str(forum.get("forum_name", "")).strip()
                canonical_name = str(forum.get("canonical_name", "")).strip()
                query_text = str(forum.get("query_text", "")).strip()
                if forum_id <= 0 or not forum_name:
                    continue

                threads = await client.get_threads(
                    forum_id,
                    rn=self.settings.max_threads_per_forum,
                )
                if getattr(threads, "err", None):
                    continue

                for thread in threads.objs:
                    raw_title = str(getattr(thread, "title", "")).strip()
                    raw_contents = getattr(thread, "contents", None)
                    raw_content_text = str(getattr(raw_contents, "text", "")).strip()
                    raw_haystack = f"{raw_title}\n{raw_content_text}"
                    if not should_keep_text(raw_haystack, rules):
                        continue
                    hits = matched_term_names(raw_haystack, rules)
                    if not self._has_entity_hit(hits, rules):
                        continue
                    collected.append(
                        self._thread_to_item(
                            thread,
                            forum_name=forum_name,
                            query_text=query_text,
                            canonical_name=canonical_name,
                            content_text=raw_content_text,
                        )
                    )

        return collected

    def _thread_to_item(
        self,
        thread: object,
        *,
        forum_name: str,
        query_text: str,
        canonical_name: str,
        content_text: str,
    ) -> CollectedItem:
        title = str(getattr(thread, "title", "")).strip()
        create_time = getattr(thread, "create_time", 0) or 0
        publish_time = (
            datetime.fromtimestamp(int(create_time)) if int(create_time) > 0 else None
        )
        reply_num = int(getattr(thread, "reply_num", 0) or 0)
        return CollectedItem(
            source=self.name,
            title=f"贴吧帖子: {title}",
            url=f"https://tieba.baidu.com/p/{int(getattr(thread, 'tid', 0) or 0)}",
            content_excerpt=content_text,
            author=str(getattr(getattr(thread, "user", None), "show_name", "")).strip(),
            publish_time=publish_time,
            tags=[
                "community",
                "tieba",
                "thread",
                forum_name,
                canonical_name,
                f"reply_num:{reply_num}",
                f"query:{query_text}",
            ],
            raw_payload=f"forum_id={int(getattr(thread, 'fid', 0) or 0)}",
        )

    def _has_entity_hit(self, hits: list[str], rules: KeywordRules) -> bool:
        categories_by_name = {term.name: term.category for term in rules.terms}
        return any(categories_by_name.get(hit) in {"team", "player"} for hit in hits)

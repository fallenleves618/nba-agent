from __future__ import annotations

from nba_agent.collectors.base import BaseCollector
from nba_agent.collectors.hupu_parser import parse_detail_page, parse_list_page
from nba_agent.http import fetch_text
from nba_agent.models import CollectedItem, HupuSettings, HupuSource, KeywordRules
from nba_agent.pipeline.keywords import should_keep_text


class HupuCollector(BaseCollector):
    name = "hupu"

    def __init__(self, settings: HupuSettings) -> None:
        self.settings = settings

    def collect(self, rules: KeywordRules) -> list[CollectedItem]:
        raw_items: list[CollectedItem] = []

        for source in self._expanded_sources():
            if not source.enabled:
                continue
            source_name = source.name
            url = source.url
            html = fetch_text(url)
            if not html:
                continue

            parsed_items = parse_list_page(html, source=source_name, base_url=url)
            parsed_items = [
                item for item in parsed_items if should_keep_text(item.title, rules)
            ]

            raw_items.extend(parsed_items[: source.max_items])

        hydrated = self._hydrate_details(raw_items)
        for item in hydrated:
            item.source = self.name
            if not item.tags:
                item.tags = ["community", "hupu"]
        return hydrated

    def _expanded_sources(self) -> list[HupuSource]:
        sources = list(self.settings.list_sources)
        for preset in self.settings.team_presets:
            source_name = self.settings.zone_template.name_template.format(
                key=preset.key,
                slug=preset.slug,
                label=preset.label,
            )
            source_url = self.settings.zone_template.url_template.format(
                key=preset.key,
                slug=preset.slug,
                label=preset.label,
            )
            sources.append(
                HupuSource(
                    name=source_name,
                    url=source_url,
                    enabled=preset.enabled,
                    max_items=preset.max_items,
                )
            )
        return sources

    def _hydrate_details(self, items: list[CollectedItem]) -> list[CollectedItem]:
        hydrated: list[CollectedItem] = []
        seen_urls: set[str] = set()

        for index, item in enumerate(items):
            if item.url in seen_urls:
                continue
            seen_urls.add(item.url)

            if index < self.settings.max_detail_fetches:
                detail_html = fetch_text(item.url)
                detail_data = parse_detail_page(detail_html)
                if detail_data.get("content_excerpt"):
                    item.content_excerpt = str(detail_data["content_excerpt"])
                if detail_data.get("publish_time"):
                    item.publish_time = detail_data["publish_time"]  # type: ignore[assignment]
                if detail_data.get("author"):
                    item.author = str(detail_data["author"])
                if detail_data.get("title"):
                    item.title = str(detail_data["title"])
                item.raw_payload = item.url

            hydrated.append(item)

        return hydrated

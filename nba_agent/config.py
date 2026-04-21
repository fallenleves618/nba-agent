from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from nba_agent.models import (
    AgentFilterSettings,
    DeliveryChannelSettings,
    DeliverySettings,
    HupuSettings,
    HupuSource,
    HupuTeamPreset,
    HupuZoneTemplate,
    KeywordRules,
    KeywordTerm,
    ReportSettings,
    TiebaSettings,
)


@dataclass
class Settings:
    base_dir: Path
    db_path: Path
    keywords_path: Path
    hupu_path: Path
    tieba_path: Path
    agent_filter_path: Path
    delivery_path: Path
    report_path: Path


def load_settings(base_dir: Path | None = None) -> Settings:
    project_dir = (base_dir or Path(__file__).resolve().parent.parent).resolve()
    return Settings(
        base_dir=project_dir,
        db_path=project_dir / "data" / "nba_agent.db",
        keywords_path=project_dir / "config" / "keywords.json",
        hupu_path=project_dir / "config" / "hupu.json",
        tieba_path=project_dir / "config" / "tieba.json",
        agent_filter_path=project_dir / "config" / "agent_filter.json",
        delivery_path=project_dir / "config" / "delivery.json",
        report_path=project_dir / "config" / "report.json",
    )


def _expand_env(value: str) -> str:
    expanded = os.path.expandvars(value).strip()
    if "${" in expanded or "$" in expanded:
        return ""
    return expanded


def load_keyword_rules(path: Path) -> KeywordRules:
    data = json.loads(path.read_text(encoding="utf-8"))
    terms = [
        KeywordTerm(
            name=term["name"],
            category=term.get("category", "generic"),
            aliases=term.get("aliases", []),
            weak_aliases=term.get("weak_aliases", []),
            exclude_aliases=term.get("exclude_aliases", []),
        )
        for term in data.get("terms", [])
        if term.get("name")
    ]
    return KeywordRules(
        include_any=data.get("include_any", []),
        exclude_any=data.get("exclude_any", []),
        groups=data.get("groups", []),
        terms=terms,
    )


def load_hupu_settings(path: Path) -> HupuSettings:
    data = json.loads(path.read_text(encoding="utf-8"))
    sources = [
        HupuSource(
            name=source["name"],
            url=source["url"],
            enabled=source.get("enabled", True),
            max_items=source.get("max_items", 20),
        )
        for source in data.get("list_sources", [])
        if source.get("name") and source.get("url")
    ]
    zone_template_data = data.get("zone_template", {})
    zone_template = HupuZoneTemplate(
        name_template=zone_template_data.get(
            "name_template", "hupu_team_zone_{key}"
        ),
        url_template=zone_template_data.get(
            "url_template", "https://bbs.hupu.com/{slug}"
        ),
    )
    team_presets = [
        HupuTeamPreset(
            key=preset["key"],
            label=preset.get("label", preset["key"]),
            slug=preset["slug"],
            enabled=preset.get("enabled", False),
            max_items=preset.get("max_items", 20),
        )
        for preset in data.get("team_presets", [])
        if preset.get("key") and preset.get("slug")
    ]
    return HupuSettings(
        list_sources=sources,
        max_detail_fetches=data.get("max_detail_fetches", 12),
        zone_template=zone_template,
        team_presets=team_presets,
    )


def load_report_settings(path: Path) -> ReportSettings:
    data = json.loads(path.read_text(encoding="utf-8"))
    per_source_top_n = data.get("per_source_top_n")
    if per_source_top_n is not None:
        per_source_top_n = int(per_source_top_n)
        if per_source_top_n <= 0:
            per_source_top_n = None
    return ReportSettings(
        overview_top_n=max(1, int(data.get("overview_top_n", 10))),
        category_top_n=max(1, int(data.get("category_top_n", 8))),
        per_source_top_n=per_source_top_n,
    )


def load_tieba_settings(path: Path) -> TiebaSettings:
    data = json.loads(path.read_text(encoding="utf-8"))
    query_categories = [
        str(category)
        for category in data.get("query_categories", ["team", "player"])
        if str(category)
    ]
    if not query_categories:
        query_categories = ["team", "player"]
    return TiebaSettings(
        enabled=bool(data.get("enabled", True)),
        max_forums_per_query=max(1, int(data.get("max_forums_per_query", 3))),
        query_categories=query_categories,
        experimental_thread_fetch_enabled=bool(
            data.get("experimental_thread_fetch_enabled", False)
        ),
        experimental_thread_fetch_mode=str(
            data.get("experimental_thread_fetch_mode", "ws")
        ),
        max_forums_for_threads=max(1, int(data.get("max_forums_for_threads", 4))),
        max_threads_per_forum=max(1, int(data.get("max_threads_per_forum", 10))),
    )


def load_agent_filter_settings(path: Path) -> AgentFilterSettings:
    data = json.loads(path.read_text(encoding="utf-8"))
    return AgentFilterSettings(
        enabled=bool(data.get("enabled", False)),
        summary_enabled=bool(data.get("summary_enabled", False)),
        api_base_url=_expand_env(str(data.get("api_base_url", ""))),
        api_key=_expand_env(str(data.get("api_key", ""))),
        model=_expand_env(str(data.get("model", ""))),
        api_mode=str(data.get("api_mode", "chat_completions")).strip() or "chat_completions",
        reasoning_effort=_expand_env(str(data.get("reasoning_effort", ""))),
        timeout_seconds=max(5.0, float(data.get("timeout_seconds", 20.0))),
        batch_size=max(1, int(data.get("batch_size", 8))),
        min_score=max(1, min(10, int(data.get("min_score", 6)))),
        summary_top_n=max(3, int(data.get("summary_top_n", 8))),
    )


def load_delivery_settings(path: Path) -> DeliverySettings:
    data = json.loads(path.read_text(encoding="utf-8"))

    def parse_channel(channel_data: object) -> DeliveryChannelSettings:
        channel_map = channel_data if isinstance(channel_data, dict) else {}
        return DeliveryChannelSettings(
            enabled=bool(channel_map.get("enabled", False)),
            webhook_url=_expand_env(str(channel_map.get("webhook_url", ""))),
            secret=_expand_env(str(channel_map.get("secret", ""))),
            msg_type=str(channel_map.get("msg_type", "text")),
        )

    console_enabled = True
    console_map = data.get("console", {})
    if isinstance(console_map, dict):
        console_enabled = bool(console_map.get("enabled", True))

    return DeliverySettings(
        console_enabled=console_enabled,
        feishu=parse_channel(data.get("feishu", {})),
        wecom=parse_channel(data.get("wecom", {})),
    )

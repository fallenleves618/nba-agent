from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class KeywordTerm:
    name: str
    category: str = "generic"
    aliases: list[str] = field(default_factory=list)
    weak_aliases: list[str] = field(default_factory=list)
    exclude_aliases: list[str] = field(default_factory=list)


@dataclass
class CollectedItem:
    source: str
    title: str
    url: str
    content_excerpt: str = ""
    author: str = ""
    publish_time: datetime | None = None
    tags: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    matched_categories: list[str] = field(default_factory=list)
    matched_groups: list[list[str]] = field(default_factory=list)
    score: int = 0
    agent_score: int | None = None
    agent_reason: str = ""
    raw_payload: str = ""


@dataclass
class ScoreGame:
    game_id: str
    game_date: datetime
    game_status: int
    game_status_text: str
    away_team: str
    away_score: int
    home_team: str
    home_score: int
    series_text: str = ""


@dataclass
class KeywordRules:
    include_any: list[str]
    exclude_any: list[str]
    groups: list[list[str]]
    terms: list[KeywordTerm] = field(default_factory=list)


@dataclass
class DailyRunResult:
    collected_count: int
    kept_count: int
    deduped_count: int
    agent_kept_count: int
    stored_count: int
    report: str
    diagnostics: list[str] = field(default_factory=list)
    stage_timings: dict[str, float] = field(default_factory=dict)


@dataclass
class HupuSource:
    name: str
    url: str
    enabled: bool = True
    max_items: int = 20


@dataclass
class HupuTeamPreset:
    key: str
    label: str
    slug: str
    enabled: bool = False
    max_items: int = 20


@dataclass
class HupuZoneTemplate:
    name_template: str = "hupu_team_zone_{key}"
    url_template: str = "https://bbs.hupu.com/{slug}"


@dataclass
class HupuSettings:
    list_sources: list[HupuSource] = field(default_factory=list)
    max_detail_fetches: int = 12
    zone_template: HupuZoneTemplate = field(default_factory=HupuZoneTemplate)
    team_presets: list[HupuTeamPreset] = field(default_factory=list)


@dataclass
class TiebaSettings:
    enabled: bool = True
    max_forums_per_query: int = 3
    query_categories: list[str] = field(default_factory=lambda: ["team", "player"])
    experimental_thread_fetch_enabled: bool = False
    experimental_thread_fetch_mode: str = "ws"
    max_forums_for_threads: int = 4
    max_threads_per_forum: int = 10


@dataclass
class DeliveryChannelSettings:
    enabled: bool = False
    webhook_url: str = ""
    secret: str = ""
    msg_type: str = "text"


@dataclass
class DeliverySettings:
    console_enabled: bool = True
    feishu: DeliveryChannelSettings = field(default_factory=DeliveryChannelSettings)
    wecom: DeliveryChannelSettings = field(default_factory=DeliveryChannelSettings)


@dataclass
class ReportSettings:
    overview_top_n: int = 10
    category_top_n: int = 8
    per_source_top_n: int | None = None


@dataclass
class AgentFilterSettings:
    enabled: bool = False
    summary_enabled: bool = False
    api_base_url: str = ""
    api_key: str = ""
    model: str = ""
    api_mode: str = "chat_completions"
    reasoning_effort: str = ""
    timeout_seconds: float = 20.0
    batch_size: int = 8
    min_score: int = 6
    summary_top_n: int = 8

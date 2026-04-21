from __future__ import annotations

from datetime import datetime, timedelta

from nba_agent.collectors.base import BaseCollector
from nba_agent.models import CollectedItem, KeywordRules


class DemoCollector(BaseCollector):
    name = "demo"

    def collect(self, rules: KeywordRules) -> list[CollectedItem]:
        now = datetime.now()
        return [
            CollectedItem(
                source=self.name,
                title="湖人交易流言升温，社区讨论热度上升",
                url="https://example.com/demo/lakers-trade-1",
                content_excerpt="多名球迷在讨论湖人是否会继续补强锋线。",
                author="demo_bot",
                publish_time=now - timedelta(minutes=20),
            ),
            CollectedItem(
                source=self.name,
                title="库里赛后采访提到恢复情况，复出时间仍待确认",
                url="https://example.com/demo/curry-return-1",
                content_excerpt="讨论集中在库里复出窗口和勇士轮换变化。",
                author="demo_bot",
                publish_time=now - timedelta(hours=1),
            ),
            CollectedItem(
                source=self.name,
                title="湖人交易流言升温，社区讨论热度上升",
                url="https://example.com/demo/lakers-trade-1?dup=true",
                content_excerpt="重复样本，用于验证标题去重。",
                author="demo_bot",
                publish_time=now - timedelta(minutes=18),
            ),
            CollectedItem(
                source=self.name,
                title="英超转会传闻持续发酵",
                url="https://example.com/demo/football-1",
                content_excerpt="这条内容应该被排除词过滤掉。",
                author="demo_bot",
                publish_time=now - timedelta(hours=2),
            ),
        ]

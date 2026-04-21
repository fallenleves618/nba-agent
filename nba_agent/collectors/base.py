from __future__ import annotations

from abc import ABC, abstractmethod

from nba_agent.models import CollectedItem, KeywordRules


class BaseCollector(ABC):
    name: str

    @abstractmethod
    def collect(self, rules: KeywordRules) -> list[CollectedItem]:
        """Collect raw items from one source."""

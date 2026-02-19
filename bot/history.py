from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class HistoryRecord:
    timestamp: datetime
    input_snippet: str
    source_language: str
    targets: tuple[str, ...]


class TranslationHistory:
    def __init__(self, *, enabled: bool, limit: int) -> None:
        self._enabled = enabled
        self._limit = limit
        self._store: dict[int, deque[HistoryRecord]] = defaultdict(
            lambda: deque(maxlen=self._limit)
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    def add(
        self,
        *,
        user_id: int,
        input_text: str,
        source_language: str,
        requested_targets: list[str],
    ) -> None:
        if not self._enabled:
            return

        snippet = input_text.strip().replace("\n", " ")
        snippet = (snippet[:77] + "...") if len(snippet) > 80 else snippet

        record = HistoryRecord(
            timestamp=datetime.now(timezone.utc),
            input_snippet=snippet,
            source_language=source_language,
            targets=tuple(requested_targets),
        )
        self._store[user_id].appendleft(record)

    def latest(self, *, user_id: int, limit: int) -> list[HistoryRecord]:
        if not self._enabled:
            return []
        return list(self._store.get(user_id, deque()))[:limit]

"""Subject progress calculation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from database.connection import get_session
from repositories import progress_repository as pr

_MOSCOW_TZ = ZoneInfo("Europe/Moscow")
_ACADEMIC_HOURS_PER_PAIR = 2


@dataclass(frozen=True)
class ProgressItem:
    title: str
    lesson_type: str
    subgroup: str | None
    completed_hours: int
    total_hours: int

    @property
    def percent(self) -> float:
        return self.completed_hours / self.total_hours * 100


def get_progress(
    group_id: int,
    user_subgroup: str | None,
    now: datetime | None = None,
) -> list[ProgressItem]:
    """Calculate cumulative progress for configured subject targets."""
    current = now or datetime.now(_MOSCOW_TZ)

    with get_session() as session:
        targets = pr.get_targets(session, group_id, user_subgroup)
        counts = pr.get_completed_lesson_counts(session, group_id, current)

    result: list[ProgressItem] = []
    for target in targets:
        key = (target.title, target.lesson_type, target.subgroup)
        completed_hours = counts.get(key, 0) * _ACADEMIC_HOURS_PER_PAIR
        result.append(ProgressItem(
            title=target.title,
            lesson_type=target.lesson_type,
            subgroup=target.subgroup or None,
            completed_hours=completed_hours,
            total_hours=target.total_hours,
        ))
    return result

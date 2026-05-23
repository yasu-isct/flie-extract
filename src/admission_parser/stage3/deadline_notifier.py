from __future__ import annotations

from datetime import date, datetime
from typing import Iterable

from admission_parser.schemas import ApplicationPeriod, DeadlineRule


def upcoming_deadline_messages(
    periods: Iterable[ApplicationPeriod],
    today: date | None = None,
) -> list[str]:
    today = today or date.today()
    messages: list[str] = []
    for period in periods:
        if not period.end_date:
            continue
        end = datetime.fromisoformat(period.end_date).date()
        days_left = (end - today).days
        if period.deadline_rule == DeadlineRule.must_arrive and days_left in (3, 2, 0):
            messages.append(
                f"{period.period_type}: {end.isoformat()} 必着。材料が期限までに到着するよう確認してください。"
            )
        elif period.deadline_rule == DeadlineRule.postmark_valid and days_left == 0:
            messages.append(
                f"{period.period_type}: 本日 {end.isoformat()} が消印有効期限です。投函状況を確認してください。"
            )
    return messages

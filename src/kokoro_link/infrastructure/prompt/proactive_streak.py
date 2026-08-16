"""Shared prompt fragment: the consecutive-unanswered proactive streak.

Both the proactive decider and the intention judge surface the same
fact — "the character has pushed N times in a row without a reply" — so
the phrasing lives here to stop the two prompt paths from drifting (one
nudging the character to escalate while the other nudges retreat for
the very same streak).

Why this exists at all (the "跳針" bug): the per-message reply tag
("（對方還沒回）") only tells the model *that* the last push went
unanswered, and the old instructions then said "basically stay silent".
With no sense of *how many times in a row* it had been ignored — and no
licence to let that land emotionally — the character re-derived a
near-identical opener every day instead of evolving (mild interest →
worry → sulking → giving space), which reads as a broken record.

LLM-first stance: this is a **fact layer**. It states the
count and opens the door to a persona-driven reaction. It must never
encode "N >= 3 → get angry"; direction and intensity are always the
model's call from persona + disposition + current state.
"""

from __future__ import annotations

from datetime import datetime


def render_unanswered_streak_lines(
    streak: int,
    *,
    latest_sent_at: datetime | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Render the unanswered-message fact layer for one or more pushes.

    A single unanswered push is useful context too: it tells the model that
    temporary silence is normal, while elapsed time distinguishes initial
    restraint from a later, genuine relational change. It never instructs the
    model to send a message.
    """
    if streak <= 0:
        return []
    elapsed = _format_elapsed(latest_sent_at=latest_sent_at, now=now)
    count = "一則" if streak == 1 else f"{streak} 則"
    first = (
        "尚未獲回應（事實）：自對方上次發話以來，你已經主動傳了 "
        f"{count}訊息，仍沒有新的回覆。"
    )
    if elapsed:
        first += f" 最近一則是在{elapsed}送出的。"
    lines = [first]
    if latest_sent_at is not None and now is not None:
        age_seconds = max(0.0, (now - latest_sent_at).total_seconds())
        if age_seconds >= 2 * 60 * 60:
            lines.append(
                "這段沉默已經過了一段時間；依角色性格，關心、想修復關係、"
                "受傷或給空間，都可能形成真正新的心境。這是可以重新衡量的動機，"
                "不是必須再發一則訊息。"
            )
        else:
            lines.append(
                "暫時沒有回覆是正常資訊，不等於被拒絕，也不等於只能沉默。"
                "先看這次是否有獨立而自然的動機。"
            )
    else:
        lines.append(
            "暫時沒有回覆是正常資訊，不等於被拒絕，也不等於只能沉默。"
        )
    lines.append(
        "唯一的硬規則：不要用同樣的語氣、同樣的題材、同樣的問題再重來一次。"
        "若你選擇再開口，必須是真正不同的方向、角度或隨時間演變的新心境；"
        "系統沒有讀取狀態，不可聲稱對方已讀。"
    )
    return lines


def _format_elapsed(*, latest_sent_at: datetime | None, now: datetime | None) -> str:
    if latest_sent_at is None or now is None:
        return ""
    seconds = max(0.0, (now - latest_sent_at).total_seconds())
    if seconds < 60 * 60:
        return f"約 {max(1, round(seconds / 60))} 分鐘前"
    hours = seconds / (60 * 60)
    if hours < 24:
        return f"約 {hours:.1f} 小時前"
    return f"約 {hours / 24:.1f} 天前"

"""LLM-backed schedule planner.

Given a character and a civil date, asks the model to emit a JSON array
of activity blocks. The parser is tolerant of the usual LLM foibles
(code fences, preambles, trailing commentary) via the shared
``parse_memory_payload`` helper.

Post-processing:

- times are parsed from ``HH:MM`` 24-hour strings
- overlapping blocks are trimmed (later block wins)
- blocks outside the target day are dropped
- categories are passed through as free-form strings (no enum)
- if the model returns nothing usable, a graceful empty schedule is
  returned so the chat flow keeps working
"""

from __future__ import annotations

from dataclasses import replace
import logging
import re
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any

from kokoro_link.application.services.model_resolver import ModelResolver
from kokoro_link.infrastructure.llm.cloud_refusal import (
    log_auxiliary_llm_failure,
)
from kokoro_link.contracts.active_llm import ActiveLLMProviderPort
from kokoro_link.contracts.llm import ChatModelPort
from kokoro_link.contracts.schedule_planner import SchedulePlannerPort
from kokoro_link.domain.entities.behavioral_pattern import BehavioralPattern
from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.schedule import (
    DailySchedule,
    MeetingAffordance,
    OPERATOR_CONFIRMED_SHARED_ROLE,
    OPERATOR_CONFIRMED_LAPSED_ROLE,
    OPERATOR_INVITE_EXPIRED_ROLE,
    OPERATOR_INVITE_PENDING_ROLE,
    OPERATOR_WISH_ROLE,
    ScenePrivacy,
    ScheduleActivity,
)
from kokoro_link.domain.services.recent_activity_digest import (
    RecentDayActivities,
)
from kokoro_link.domain.value_objects.actor import ParticipantRef
from kokoro_link.domain.entities.story_arc import StoryArcBeat
from kokoro_link.domain.entities.story_event import StoryEvent
from kokoro_link.infrastructure.prompt.character_identity import (
    render_character_identity_lines,
)
from kokoro_link.infrastructure.prompt.operator_language import (
    render_operator_language_hint,
)
from kokoro_link.infrastructure.prompt.role_boundary import (
    render_role_knowledge_boundary_lines,
)
from kokoro_link.infrastructure.memory.json_parser import parse_memory_payload
from kokoro_link.infrastructure.prompts import get_default_loader

_LOGGER = logging.getLogger(__name__)

_MAX_ACTIVITIES = 14
_MIN_ACTIVITIES = 4
_MAX_DESCRIPTION_CHARS = 120
_MAX_CATEGORY_CHARS = 40
_MAX_LOCATION_CHARS = 80
_MAX_COMPANION_NAMES_PER_ACTIVITY = 3
_MAX_COMPANION_NAME_CHARS = 40

_GENERIC_OPERATOR_REFERENCE_NAMES = (
    "使用者",
    "玩家",
    "你",
    "user",
    "player",
    "the user",
    "the player",
    "ユーザー",
    "あなた",
)

# A reference to an explicitly later day is a preparation or anticipation
# fact, not evidence that the operator is already present in today's scene.
# Keep this narrowly local to an otherwise direct co-presence match so an
# unrelated "明天" elsewhere in a long activity does not weaken the guard.
_FUTURE_REFERENCE_MARKERS = (
    "明天",
    "明日",
    "翌日",
    "隔天",
    "明後日",
    "下週",
    "下周",
    "tomorrow",
    "the next day",
)
_CURRENT_REFERENCE_MARKERS = (
    "今天",
    "今日",
    "今晚",
    "現在",
    "當下",
    "today",
    "tonight",
    "now",
)

# These are deliberately concrete co-presence actions, not a loose bag of
# relationship words. A gap-day preparation may truthfully mention the player
# (for example, preparing an outfit for a later date); only a claim that the
# player is already present must be rejected.
_DIRECT_SHARED_EVENT_ACTIONS = (
    "見面|碰面|會面|約會|赴約|相約|會合|同行|相聚|牽手|擁抱|"
    "逛(?:街|夏祭|展覽|市集)?|吃(?:飯|晚餐|午餐)?|看(?:電影|展覽)?|"
    "參加|出席|到場|共度"
)

# A future beat containing one of these terms denotes a physical event rather
# than a purely conversational scene.  The terms become anchors only when
# they occur in that future beat; they are not global bans on ordinary days.
_FUTURE_PHYSICAL_EVENT_TERMS = (
    "夏祭",
    "文化祭",
    "祭典",
    "展覽",
    "演唱會",
    "市集",
    "活動會場",
    "線下會場",
    "線下活動",
    "festival",
    "exhibition",
    "concert",
    "market",
    "offline event",
    "in-person event",
)

_FUTURE_EVENT_ATTENDANCE_ACTIONS = re.compile(
    r"前往|抵達|到達|進入|入場|出席|參加|造訪|探訪|踩點|勘景|"
    r"使用|逛|參觀|遊覽|排隊|等待|停留|待在|攤位|表演區|"
    r"travel to|arrive|enter|attend|visit|queue|wait|browse",
    re.IGNORECASE,
)

# SE1 — bounds on the story-event inspiration block. Narratives are 2–3
# sentences by contract but the expander is an LLM, so both axes are
# clamped: at most this many events (most recent win) and at most this
# many characters per narrative. Together they cap the block near the
# weight of the recent-activity digest it sits beside.
_MAX_STORY_EVENTS = 8
_MAX_STORY_EVENT_NARRATIVE_CHARS = 160

_WEEKDAY_LABELS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


class LLMSchedulePlanner(SchedulePlannerPort):
    def __init__(
        self,
        model: ChatModelPort | None = None,
        *,
        provider: ActiveLLMProviderPort | None = None,
        feature_key: str | None = None,
    ) -> None:
        self._resolver = ModelResolver(
            provider=provider, model=model, feature_key=feature_key,
        )

    async def plan_day(
        self,
        *,
        character: Character,
        date_: date,
        local_tz: tzinfo,
        recent_dialogue_summary: str = "",
        today_beat: StoryArcBeat | None = None,
        upcoming_beats: tuple[StoryArcBeat, ...] = (),
        world_context: str = "",
        calendar_context: str = "",
        weather_context: str = "",
        operator_relationship_context: str = "",
        operator_persona_lines: tuple[str, ...] = (),
        schedule_involvement_policy: str = "none",
        pre_committed_activities: tuple[ScheduleActivity, ...] = (),
        expired_operator_commitments: tuple[ScheduleActivity, ...] = (),
        recent_activity_digest: tuple[RecentDayActivities, ...] = (),
        recent_story_events: tuple[StoryEvent, ...] = (),
        recurring_patterns: tuple[BehavioralPattern, ...] = (),
        operator_primary_language: str = "zh-TW",
        operator_reference_names: tuple[str, ...] = (),
    ) -> DailySchedule:
        future_beats = tuple(
            beat
            for beat in (today_beat, *upcoming_beats)
            if beat is not None and beat.scheduled_date > date_
        )
        if future_beats:
            # A prior bad plan can carry an ``operator_wish`` forward as a
            # live commitment during manual regeneration. It must not bypass
            # the gap-day venue guard, while a genuinely confirmed shared
            # slot remains authoritative.
            pre_committed_activities = (
                _drop_unconfirmed_early_future_event_venue_commitments(
                    pre_committed_activities,
                    future_beats=future_beats,
                )
            )
        if await self._resolver.is_fake(character=character):
            # Even with the fake provider we honour chat-extracted
            # commitments — otherwise local dev would silently drop
            # them. Mark the schedule planned so ensure_schedule short-
            # circuits going forward.
            return DailySchedule.create(
                character_id=character.id,
                date_=date_,
                activities=list(pre_committed_activities),
                is_planned=True,
            )
        prompt = _build_prompt(
            character=character, date_=date_,
            recent_dialogue_summary=recent_dialogue_summary,
            today_beat=today_beat,
            upcoming_beats=upcoming_beats,
            world_context=world_context,
            calendar_context=calendar_context,
            weather_context=weather_context,
            operator_relationship_context=operator_relationship_context,
            operator_persona_lines=operator_persona_lines,
            schedule_involvement_policy=schedule_involvement_policy,
            pre_committed_activities=pre_committed_activities,
            expired_operator_commitments=expired_operator_commitments,
            recent_activity_digest=recent_activity_digest,
            recent_story_events=recent_story_events,
            recurring_patterns=recurring_patterns,
            local_tz=local_tz,
            operator_primary_language=operator_primary_language,
        )
        try:
            raw = await self._resolver.generate(prompt, character=character)
        except Exception as exc:
            log_auxiliary_llm_failure(
                _LOGGER, exc, "Schedule planner LLM call failed",
            )
            # Preserve pre-commitments, but make the attempt terminal for this
            # civil day. Automatic every-tick retries can multiply one upstream
            # outage into unbounded paid traffic; the explicit regenerate path
            # is the controlled retry surface.
            return DailySchedule.create(
                character_id=character.id,
                date_=date_,
                activities=list(pre_committed_activities),
                is_planned=True,
            )

        entries = parse_memory_payload(raw)
        activities = _build_activities(
            entries,
            date_=date_,
            local_tz=local_tz,
            operator_primary_language=operator_primary_language,
        )
        if future_beats:
            # A future beat is useful preparation context, but it is not
            # permission to materialise either the player scene or the
            # physical event venue early. Keep solo preparation; remove only
            # direct player co-presence and premature venue attendance.
            activities = _drop_unconfirmed_future_operator_events(
                activities,
                operator_reference_names=operator_reference_names,
                pre_committed_activities=pre_committed_activities,
            )
            activities = _drop_early_future_event_venue_activities(
                activities,
                future_beats=future_beats,
            )
        # Defensive merge: if the LLM ignored the commitment directive
        # and didn't emit one of the pre-commitments, splice them back
        # in. ``_resolve_overlaps`` style logic isn't needed here because
        # ``_build_activities`` already trimmed overlaps among the LLM's
        # output; for the splice we keep commitments fixed and trim
        # surrounding LLM activities to avoid covering them.
        activities = _merge_pre_commitments(
            activities, pre_committed_activities,
        )
        return DailySchedule.create(
            character_id=character.id,
            date_=date_,
            activities=activities,
            is_planned=True,
        )


def _build_prompt(
    *,
    character: Character,
    date_: date,
    recent_dialogue_summary: str = "",
    today_beat: StoryArcBeat | None = None,
    upcoming_beats: tuple[StoryArcBeat, ...] = (),
    world_context: str = "",
    calendar_context: str = "",
    weather_context: str = "",
    operator_relationship_context: str = "",
    operator_persona_lines: tuple[str, ...] = (),
    schedule_involvement_policy: str = "none",
    pre_committed_activities: tuple[ScheduleActivity, ...] = (),
    expired_operator_commitments: tuple[ScheduleActivity, ...] = (),
    recent_activity_digest: tuple[RecentDayActivities, ...] = (),
    recent_story_events: tuple[StoryEvent, ...] = (),
    recurring_patterns: tuple[BehavioralPattern, ...] = (),
    local_tz: tzinfo | None = None,
    operator_primary_language: str = "zh-TW",
) -> str:
    weekday = _WEEKDAY_LABELS[date_.weekday()]
    personality = "、".join(character.personality) or "（未設定）"
    interests = "、".join(character.interests) or "（未設定）"
    aspirations = "、".join(character.aspirations) if character.aspirations else "（未設定）"
    companions_block = _render_companions_block(character)
    identity_block = "\n".join(render_character_identity_lines(character))
    personality_type_block = "\n".join(character.personality_type.to_prompt_lines())
    knowledge_boundary_block = "\n".join(
        render_role_knowledge_boundary_lines(),
    )
    calendar_block = (
        "\n今日真實世界行事曆：\n" + calendar_context.strip() + "\n"
        if calendar_context.strip()
        else ""
    )
    # The caveat rides with the facts rather than sitting in the template's
    # principles, so it only ever appears when there *are* facts to qualify
    # (future-day pre-plans pass an empty context on purpose).
    weather_block = (
        "\n此刻真實世界天氣（此為規劃當下的即時事實，當天天氣可能變化）：\n"
        + weather_context.strip()
        + "\n"
        if weather_context.strip()
        else ""
    )
    has_living_arrangement = _relationship_context_has_living_arrangement(
        operator_relationship_context,
    )
    operator_context_block = _render_operator_context_block(
        relationship_context=operator_relationship_context,
        operator_persona_lines=operator_persona_lines,
        schedule_involvement_policy=schedule_involvement_policy,
    )
    commitments_block = _render_commitments_block(
        pre_committed_activities, local_tz=local_tz,
    )
    expired_commitments_block = _render_expired_commitments_block(
        expired_operator_commitments, local_tz=local_tz,
    )
    patterns_block = _render_recurring_patterns_block(recurring_patterns)
    recent_activity_block = _render_recent_activity_block(recent_activity_digest)
    story_events_block = _render_story_events_block(recent_story_events)
    dialogue_block = (
        "\n近期對話脈絡（這位角色最近跟使用者在聊的事，行程請盡量呼應、"
        "避免與剛達成的共識或約定相衝突）：\n"
        + recent_dialogue_summary.strip()
        + "\n"
        if recent_dialogue_summary.strip()
        else ""
    )
    arc_block = _render_arc_block(
        target_date=date_,
        today_beat=today_beat,
        upcoming_beats=upcoming_beats,
    )
    world_block = (
        "\n" + world_context.strip() + "\n"
        if world_context.strip()
        else ""
    )
    location_rule_lines = [
        "- location 可選；若沒有特別想法可省略或給空字串。",
    ]
    if world_context.strip():
        # World present — rules become stricter so the character lives
        # in real places not invented placeholders.
        location_rule_lines = [
            "- **location 規則（重要）**：",
            "  · 如果世界裡已經有對應的地點（見下方既有地點清單），**直接使用清單裡的名稱**，不要造同義詞。",
            "  · 角色私人空間（家、租屋處、房間、公寓、宿舍）必須命名為「"
            f"{character.name}的XXX」（例：「{character.name}的租屋處」、"
            f"「{character.name}的房間」），**不要用泛稱**「家中」「我家」「私處」這種會被多角色共用的字眼。",
            "  · 共用場所（咖啡廳、公園、車站、便利商店）優先沿用既有清單裡的名稱；"
            "清單沒有但情境需要時，給具體有特徵的名字（「澀谷站前的咖啡廳」），不要泛稱（「咖啡廳」）。",
            "  · 沒指定地點的活動（在腦中思考、發呆、線上活動）可以省略 location。",
        ]
    if has_living_arrangement:
        location_rule_lines.append(
            "- 若上方起始關係載明角色與使用者有居住安排，居家時段的 location 請命名為共同住所"
            "（例：「家（與使用者同住）」或起始關係描述的住所名稱），不要另造一間"
            f"「{character.name}的家」。外出、工作、上課、採買等時段仍照角色自己的生活安排。",
        )
    body = get_default_loader().render(
        "schedule/planner",
        date_iso=date_.isoformat(),
        weekday=weekday,
        min_activities=_MIN_ACTIVITIES,
        max_activities=_MAX_ACTIVITIES,
        location_rule_lines="\n".join(location_rule_lines),
        character_name=character.name,
        character_summary=character.summary or "（未設定）",
        identity_block=identity_block,
        personality_type_block=personality_type_block,
        personality=personality,
        interests=interests,
        aspirations=aspirations,
        companions_block=companions_block,
        knowledge_boundary_block=knowledge_boundary_block,
        calendar_block=calendar_block,
        weather_block=weather_block,
        operator_context_block=operator_context_block,
        commitments_block=commitments_block,
        expired_commitments_block=expired_commitments_block,
        dialogue_block=dialogue_block,
        world_block=world_block,
        arc_block=arc_block,
        patterns_block=patterns_block,
        recent_activity_block=recent_activity_block,
        story_events_block=story_events_block,
    )
    language_hint = render_operator_language_hint(operator_primary_language)
    if language_hint:
        body = f"{language_hint}\n\n{body}"
    return body


def _render_operator_context_block(
    *,
    relationship_context: str,
    operator_persona_lines: tuple[str, ...],
    schedule_involvement_policy: str,
) -> str:
    cleaned_relationship = (relationship_context or "").strip()
    cleaned_persona = [line.strip() for line in operator_persona_lines if line.strip()]
    policy = (schedule_involvement_policy or "none").strip().lower()
    has_living_arrangement = _relationship_context_has_living_arrangement(
        cleaned_relationship,
    )
    if not cleaned_relationship and not cleaned_persona and policy == "none":
        return ""

    lines: list[str] = [
        "",
        "使用者相關事實（只供行程合理性；不是已發生的系統內記憶，也不是角色靜態設定）：",
    ]
    if cleaned_relationship:
        lines.append(cleaned_relationship)
    if cleaned_persona:
        lines.append("使用者安全畫像（可影響話題準備，不可改寫成已約好的活動）：")
        lines.extend(cleaned_persona[:8])
    lines.append("行程中的使用者參與規則：")
    lines.extend(_schedule_involvement_policy_lines(policy, has_living_arrangement))
    lines.append("")
    return "\n".join(lines)


def _relationship_context_has_living_arrangement(relationship_context: str) -> bool:
    return any(
        line.strip().startswith("- 居住安排：")
        for line in relationship_context.splitlines()
    )


def _schedule_involvement_policy_lines(
    policy: str,
    has_living_arrangement: bool = False,
) -> list[str]:
    living_lines = []
    if has_living_arrangement:
        living_lines = [
            "- 起始關係有居住安排時，在家時段使用者自然可能在同一生活空間是環境事實，不是已約好的活動。",
            "- 不要把使用者放進 companion_names；使用者不是 NPC 配角。",
            "- 若只是想邀請或想到使用者，請使用 operator_involvement 結構欄位；不要把共同狀態寫進 description。",
            "- 與使用者親密同住（例如伴侶、同床共枕）時，夜間休息／睡眠屬共同生活，"
            "不必另切成不可打擾的獨處硬段；該時段的 scene_privacy／meeting_affordance "
            "可反映共眠同處，不要一律設成最封閉。是否為親密伴侶請依關係語意判斷，"
            "室友／家人／寵物不適用此放寬。",
        ]
    if policy == "mention_only":
        return living_lines + [
            "- 可產生：想起使用者偏好、準備下次聊天話題、整理想分享給對方的內容。",
            "- 這類活動若需要標示使用者語意，operator_involvement 請填 operator_wish。",
            "- 不可產生：不可寫成已約定見面或具體共同活動。",
        ]
    if policy == "invite_required":
        return living_lines + [
            "- 可產生：想邀請使用者、準備邀請、猶豫要不要問對方一起做某事。",
            "- 這些只是行程中的準備或念頭，operator_involvement 請填 operator_wish；description 只寫角色自己的準備或念頭，絕不可寫成已送出訊息、已問出口或正在等回覆。",
            "- 不可產生：把邀請寫成對方已答應；不可杜撰已約好的時段。",
        ]
    if policy == "shared_allowed":
        return living_lines + [
            "- 可產生：使用者明確允許的共同日常或共同時段。",
            "- planner 不得自行輸出 operator_invite_pending 或 operator_confirmed_shared；未由 chat 明確確認者只能用 operator_wish。",
            "- 不可產生：未提供的共同往事、未確認的過去約定或私密背景。",
        ]
    return living_lines + [
        "- 可產生：角色自己的日常與獨立生活。",
        "- 不可產生：把使用者排進 description、location 或 companion_names；避免「和你一起」等共同活動措辭。",
    ]


def _render_commitments_block(
    commitments: tuple[ScheduleActivity, ...],
    *,
    local_tz: tzinfo | None,
) -> str:
    """Render the "must-include" commitments block.

    These are activities the character (and the user) have already
    agreed on in chat — e.g. "明天 7 點看電影". The planner is told
    they're **fixed**: same start / end / description, no shifting, no
    omitting. The rest of the day is to be built around them.
    """
    if not commitments:
        return ""
    lines = [
        "",
        "**已既定的承諾時段（必須原封不動保留在輸出中，不要改時間、不要拔掉、"
        "不要改寫描述；其他活動請繞開不要重疊）**：",
    ]
    for act in commitments:
        start = act.start_at
        end = act.end_at
        if local_tz is not None:
            start = start.astimezone(local_tz)
            end = end.astimezone(local_tz)
        start_text = start.strftime("%H:%M")
        end_text = end.strftime("%H:%M")
        loc = f"（{act.location}）" if act.location else ""
        companions = (
            f"｜一起：{ '、'.join(act.companion_names) }"
            if act.companion_names else ""
        )
        lines.append(
            f"- {start_text}–{end_text} {act.description}{loc}{companions}"
            f"｜category={act.category}"
        )
    lines.append("")
    return "\n".join(lines)


_EXPIRED_ROLE_LABELS: dict[str, str] = {
    OPERATOR_INVITE_EXPIRED_ROLE: "當時只是邀請，使用者始終沒有答應",
    OPERATOR_CONFIRMED_LAPSED_ROLE: "當時說好了，但沒有留下真的一起完成的紀錄",
}


def _expired_status_label(activity: ScheduleActivity) -> str:
    """Describe *why* a commitment is dead, from its structured role.

    Derived from the participant role the expiry sweep stamped — never
    from reading the description — so this stays a fact projection rather
    than an interpretation of user-visible prose.
    """
    for ref in activity.participant_refs:
        label = _EXPIRED_ROLE_LABELS.get(ref.role or "")
        if label is not None:
            return label
    return "已經過去、沒有成行"


def _render_expired_commitments_block(
    commitments: tuple[ScheduleActivity, ...],
    *,
    local_tz: tzinfo | None,
) -> str:
    """Render dead invitations as a "know this, never use this" fact list.

    The counterpart to :func:`_render_commitments_block`. That block says
    "keep these exactly"; this one says "these are over". Both are needed:
    filtering the expired ones out of the input silently would leave the
    model free to re-invent them from a dialogue summary that still talks
    about the appointment — which is precisely how the same invitation kept
    reappearing on day after day after it had already failed to happen.
    """
    if not commitments:
        return ""
    lines = [
        "",
        "**已經過期、沒有成行的邀請／共同約定（事實清單，僅供你知悉，不是可用素材）**：",
    ]
    for act in commitments:
        start = act.start_at
        end = act.end_at
        if local_tz is not None:
            start = start.astimezone(local_tz)
            end = end.astimezone(local_tz)
        weekday = _WEEKDAY_LABELS[start.weekday()]
        loc = f"（{act.location}）" if act.location else ""
        lines.append(
            f"- {start.date().isoformat()}（{weekday}）"
            f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')} "
            f"{act.description}{loc}｜{_expired_status_label(act)}",
        )
    lines.append(
        "以上都已成為過去式。**不得**把其中任何一項重新排進今天的行程，也不得換個說法、"
        "換個時段、換個地點後再排一次。就算近期對話脈絡、劇情骨架或生活節奏裡又提到它們，"
        "那也只是舊話題的回音，不代表這個約定重新成立。角色心裡若仍惦記，"
        "只能安排成與使用者無關的獨自行動，operator_involvement 不得因此標成邀請或共同狀態；"
        "要重新約，必須等使用者在對話裡再次開口。",
    )
    lines.append("")
    return "\n".join(lines)


def _render_recurring_patterns_block(
    patterns: tuple[BehavioralPattern, ...],
) -> str:
    """HUMANIZATION_ROADMAP §3.3 — render observed recurrences as a
    fact-layer planner block.

    LLM-first 紅線: we surface *what was observed*, not *what to do*.
    The planner LLM decides whether to continue the rhythm or break it,
    no hardcoded "if Monday morning was coffee, schedule coffee" branch.

    Numeric ``observed_count`` is intentionally hidden — the LLM does
    not need to do arithmetic over occurrences, just sense "this is a
    stable pattern". Top-N ordering already happened in the repo.
    """
    if not patterns:
        return ""
    lines = [
        "",
        "近幾週觀察到的生活節奏（這些是「過去」的傾向，今天可以延續、可以打破，"
        "但不要全盤忽略；具體節奏由你決定）：",
    ]
    for pattern in patterns[:8]:
        lines.append(f"- {pattern.description}")
    lines.append("")
    return "\n".join(lines)


def _render_recent_activity_block(
    days: tuple[RecentDayActivities, ...],
) -> str:
    """CF5 P5a — the days just gone, as a fact list the planner reads
    before inventing today.

    The counterpart to :func:`_render_recurring_patterns_block`: that one
    says "this is your rhythm, feel free to keep it", this one says "this
    is what you already did, don't just do it again". Both are facts; the
    template's 生活素材新鮮度紀律 rules own the judgement of which
    activities the no-repeat rule covers, so nothing here inspects,
    classifies or compares descriptions — they are passed through
    verbatim, routine entries included. Hiding the routine ones would be
    the code quietly deciding what counts as routine, which is precisely
    the call the model is asked to make.

    Absolute dates (never 昨天/前天) for the same reason CF3 stamped them
    on expired commitments: a relative label read days later is how a
    stale item gets re-read as a live one.
    """
    if not days:
        return ""
    lines = [
        "",
        "最近幾天已經排過／做過的活動（事實清單；用來判斷什麼題材剛用過，"
        "不是今天要照抄的內容）：",
    ]
    for day in days:
        weekday = _WEEKDAY_LABELS[day.date.weekday()]
        joined = "、".join(day.descriptions)
        lines.append(f"- {day.date.isoformat()}（{weekday}）：{joined}")
    lines.append(
        "今天請給出新的一天：上面出現過的特色／一次性活動不要再排一次，"
        "同一個主題要再登場必須帶明確的新進展或變化並寫進 description；"
        "日常慣例（睡眠、三餐、通勤、既有習慣）不在此限，照常安排即可。",
    )
    lines.append("")
    return "\n".join(lines)


def _story_event_date_label(raw: str) -> str:
    """Absolute-date label for one story event, weekday attached.

    ``StoryEvent.date`` is a stored ISO string, not a ``date`` — a row
    that somehow holds junk falls back to the raw text rather than
    killing the whole prompt build."""
    text = raw.strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return text
    return f"{parsed.isoformat()}（{_WEEKDAY_LABELS[parsed.weekday()]}）"


def _render_story_events_block(
    events: tuple[StoryEvent, ...],
) -> str:
    """SE1 — the character's recent story events, as inspiration facts.

    The third leg of the freshness inputs: the recurring-patterns block
    says "this is your rhythm", the recent-activity block says "this is
    what you already did", and this one says "this is what recently
    *happened to you*". Story events were previously visible to chat and
    the proactive decider but never to the planner — the "planner 盲區"
    item of the stale-appointment diagnosis — so the day being planned
    could not pick up, respond to or close out anything the character
    had just lived through.

    Facts only, judgement stays with the model: narratives are passed
    through verbatim apart from whitespace-flattening and a length clamp
    (they are persisted prose re-read for days; nothing here inspects or
    classifies their content). Callers supply events oldest-first; the
    count cap keeps the most recent ones. Absolute dates for the same
    reason CF3/CF5 use them — a relative label read later is how a stale
    item gets re-read as a live one.
    """
    if not events:
        return ""
    lines = [
        "",
        "角色近日發生的小事（角色近日的親身經歷，由舊到新；靈感素材，不是指令）：",
    ]
    for event in events[-_MAX_STORY_EVENTS:]:
        narrative = " ".join(event.narrative.split())
        if len(narrative) > _MAX_STORY_EVENT_NARRATIVE_CHARS:
            narrative = narrative[:_MAX_STORY_EVENT_NARRATIVE_CHARS] + "…"
        tone = (
            f"｜當時心情：{event.emotional_tone}"
            if event.emotional_tone else ""
        )
        lines.append(
            f"- {_story_event_date_label(event.date)}：{narrative}{tone}",
        )
    lines.append(
        "今天的行程可以自然延續、回應或收尾其中的片段，也可以完全不提；"
        "要延續時請帶出新的進展或變化（見生活素材新鮮度紀律），"
        "不要把同一件事原樣重演。",
    )
    lines.append("")
    return "\n".join(lines)


def _render_companions_block(character: "Character") -> str:
    """Render the per-character companion roster for the planner prompt.

    Empty string when the character has no companions configured —— the
    planner naturally produces an all-solo schedule in that case, same
    as before this feature landed."""
    if not character.companions:
        return ""
    lines = ["", "私人 NPC 同伴（角色生活圈裡的配角，行程裡可以提到「跟他/她一起做某事」）："]
    for companion in character.companions:
        role = f"（{companion.role}）" if companion.role else ""
        blurb = f"：{companion.brief_profile}" if companion.brief_profile else ""
        rel = (
            f"｜目前關係：{companion.relationship_snippet}"
            if companion.relationship_snippet else ""
        )
        lines.append(f"- {companion.name}{role}{blurb}{rel}")
    lines.append(
        "規劃時請依場景合理性自然分配：跟室友吃晚餐、和同事下午開會、"
        "和朋友週末出去，不必每個 NPC 都登場，獨處時段也很正常。"
    )
    return "\n".join(lines)


def _render_arc_block(
    *,
    target_date: date,
    today_beat: StoryArcBeat | None,
    upcoming_beats: tuple[StoryArcBeat, ...],
) -> str:
    """Inject the active arc's scene beats into the planner prompt.

    When ``today_beat.scheduled_date == target_date`` we emit a hard
    "**必須**" directive so today's activities embed the scene. When
    the supplied ``today_beat`` is actually scheduled for a future day
    (the schedule service falls back to the next forward beat on gap
    days), we render an "anticipation/preparation" block instead — the
    planner is told the date so it doesn't stage the scene today.
    Upcoming beats are surfaced as softer context so the planner can
    leave space (rest, prep, rehearsal) for what's coming.
    """
    if today_beat is None and not upcoming_beats:
        return ""
    lines: list[str] = [""]
    is_today = (
        today_beat is not None
        and today_beat.scheduled_date == target_date
    )
    if today_beat is not None and is_today:
        lines.append("本日劇情骨架（**必須**反映在行程中）：")
        lines.append(
            f"- 今天有一場戲叫《{today_beat.title}》，"
            "請在當天行程中安排一個**對應這場戲**的時段（時間自訂、合理即可）。",
        )
        if today_beat.location:
            lines.append(f"  * 場景地點：{today_beat.location}（行程的 location 欄位請填這個）")
        if today_beat.scene_characters:
            who = "、".join(today_beat.scene_characters)
            lines.append(f"  * 出場人物：{who}（請在 description 裡帶到這些人）")
        if today_beat.dramatic_question:
            lines.append(f"  * 戲劇問題：{today_beat.dramatic_question}")
        if today_beat.summary:
            summary = today_beat.summary.strip().replace("\n", " ")
            if len(summary) > 200:
                summary = summary[:200] + "…"
            lines.append(f"  * 場景脈絡：{summary}")
        if not today_beat.required:
            lines.append("  * （此 beat 標為可選；若與性格／既有行程嚴重衝突可弱化處理）")
        lines.append(
            "  * 當天的行程要圍繞這場戲鋪陳：之前可有準備／路上的時段，"
            "之後可有結束後的反應／休息／回家路上等。不要讓這場戲變成憑空插入。",
        )
    elif today_beat is not None:
        # today_beat is from the future — gap-day fallback. Don't stage
        # the scene today; have the day prepare/anticipate instead.
        day_diff = (today_beat.scheduled_date - target_date).days
        when_text = (
            f"再 {day_diff} 天（{today_beat.scheduled_date.isoformat()}）"
            if day_diff > 0
            else today_beat.scheduled_date.isoformat()
        )
        lines.append("劇情骨架（今天沒有指定場景，請為下一場戲鋪陳／準備）：")
        lines.append(
            f"- 下一場戲是《{today_beat.title}》，預計在 {when_text} 發生。"
            "今天的行程**不要**把這場戲演出來，但可以安排一些為它做準備、"
            "心理鋪陳、或相關的日常時段（例如：練習、查資料、整理裝備、"
            "與相關人物碰面、獨處沉澱）。",
        )
        if today_beat.location:
            lines.append(
                f"  * 那場戲的地點是：{today_beat.location}"
                "（在該日期前不得前往、等待、進入、使用或勘景；"
                "準備請安排在其他地方）",
            )
        if today_beat.scene_characters:
            who = "、".join(today_beat.scene_characters)
            lines.append(f"  * 那場戲的出場人物：{who}（今天可以提及或聯絡；只有非使用者 NPC 才可安排碰面）")
        if today_beat.dramatic_question:
            lines.append(f"  * 那場戲的戲劇問題：{today_beat.dramatic_question}（今天可以醞釀情緒）")
        if today_beat.summary:
            summary = today_beat.summary.strip().replace("\n", " ")
            if len(summary) > 200:
                summary = summary[:200] + "…"
            lines.append(f"  * 那場戲的脈絡：{summary}")
        lines.append(
            "  * 若下一場戲牽涉使用者／玩家，使用者今天尚未到場、尚未參與；"
            "除非上方「已既定的承諾時段」明確列出今天的共同活動，否則不可把"
            "見面、約會、同行、牽手、共同出席等寫進今天的行程。"
        )
    if upcoming_beats:
        lines.append("- 接下來幾天即將發生（僅供參考，今天不需強行帶到，但行程可預留鋪陳空間）：")
        for beat in upcoming_beats[:2]:
            day_diff = (beat.scheduled_date - target_date).days
            when = (
                f"再 {day_diff} 天" if day_diff > 0
                else beat.scheduled_date.isoformat()
            )
            label = beat.title or "（未命名）"
            extra = f"（{beat.location}）" if beat.location else ""
            lines.append(f"  * {when}：《{label}》{extra}")
    lines.append("")
    return "\n".join(lines)


def _build_activities(
    entries: list[dict[str, Any]],
    *,
    date_: date,
    local_tz: tzinfo,
    operator_primary_language: str = "zh-TW",
) -> list[ScheduleActivity]:
    day_start = datetime.combine(date_, time(0, 0), tzinfo=local_tz)
    day_end = day_start + timedelta(days=1)

    parsed: list[
        tuple[
            datetime,
            datetime,
            str,
            str,
            str | None,
            float | None,
            tuple[str, ...],
            str | None,
            ScenePrivacy | None,
            MeetingAffordance | None,
        ]
    ] = []
    for entry in entries[: _MAX_ACTIVITIES * 2]:  # allow a little slack before hard trim
        start = _coerce_local_time(entry.get("start"), date_=date_, local_tz=local_tz)
        end = _coerce_local_time(entry.get("end"), date_=date_, local_tz=local_tz)
        if start is None or end is None:
            continue
        # Support schedules that cross midnight by clamping to day_end.
        if end <= start:
            continue
        if start >= day_end or end <= day_start:
            continue
        start = max(start, day_start)
        end = min(end, day_end)
        description = _coerce_text(entry.get("description"), limit=_MAX_DESCRIPTION_CHARS)
        category = _coerce_text(entry.get("category"), limit=_MAX_CATEGORY_CHARS)
        if not description or not category:
            continue
        location = _coerce_text(entry.get("location"), limit=_MAX_LOCATION_CHARS)
        busy = _coerce_busy(entry.get("busy_score"))
        companions = _coerce_companion_names(entry.get("companion_names"))
        operator_involvement = _coerce_operator_involvement(
            entry.get("operator_involvement"),
        )
        if operator_involvement == OPERATOR_WISH_ROLE and _claims_outbound_invitation(
            description,
        ):
            # The day planner has no delivery capability. A message claimed by
            # its prose would later become a false episodic memory, so keep the
            # private preparation but remove the invented external action.
            description = _unsent_invitation_draft(operator_primary_language)
        scene_privacy = _coerce_scene_privacy(entry.get("scene_privacy"))
        meeting_affordance = _coerce_meeting_affordance(
            entry.get("meeting_affordance"),
        )
        parsed.append(
            (
                start,
                end,
                description,
                category,
                location or None,
                busy,
                companions,
                operator_involvement,
                scene_privacy,
                meeting_affordance,
            ),
        )

    parsed.sort(key=lambda t: t[0])

    trimmed: list[
        tuple[
            datetime,
            datetime,
            str,
            str,
            str | None,
            float | None,
            tuple[str, ...],
            str | None,
            ScenePrivacy | None,
            MeetingAffordance | None,
        ]
    ] = []
    last_end: datetime | None = None
    for (
        start,
        end,
        description,
        category,
        location,
        busy,
        companions,
        operator_involvement,
        scene_privacy,
        meeting_affordance,
    ) in parsed:
        if last_end is not None and start < last_end:
            # overlap: push start forward; drop if it collapses to zero.
            start = last_end
            if end <= start:
                continue
        trimmed.append(
            (
                start,
                end,
                description,
                category,
                location,
                busy,
                companions,
                operator_involvement,
                scene_privacy,
                meeting_affordance,
            ),
        )
        last_end = end
        if len(trimmed) >= _MAX_ACTIVITIES:
            break

    return [
        ScheduleActivity.create(
            start_at=start,
            end_at=end,
            description=description,
            category=category,
            location=location,
            busy_score=busy,
            companion_names=companions,
            participant_refs=_operator_participant_refs(operator_involvement),
            scene_privacy=scene_privacy,
            meeting_affordance=meeting_affordance,
        )
        for (
            start,
            end,
            description,
            category,
            location,
            busy,
            companions,
            operator_involvement,
            scene_privacy,
            meeting_affordance,
        ) in trimmed
    ]


def _coerce_scene_privacy(raw: Any) -> ScenePrivacy | None:
    if not isinstance(raw, str):
        return None
    try:
        return ScenePrivacy(raw.strip().lower())
    except ValueError:
        return None


def _coerce_meeting_affordance(raw: Any) -> MeetingAffordance | None:
    if not isinstance(raw, str):
        return None
    try:
        return MeetingAffordance(raw.strip().lower())
    except ValueError:
        return None


def _coerce_operator_involvement(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip().lower()
    aliases = {
        # A daily plan cannot send a message. Reserve invite_pending for a
        # post-turn adjustment after the character actually made an invite in
        # chat; a planner-only draft remains an operator_wish.
        "invite_pending": OPERATOR_WISH_ROLE,
        OPERATOR_INVITE_PENDING_ROLE: OPERATOR_WISH_ROLE,
        "wish": OPERATOR_WISH_ROLE,
        OPERATOR_WISH_ROLE: OPERATOR_WISH_ROLE,
    }
    return aliases.get(value)


_OUTBOUND_INVITATION_MARKERS = (
    "最後才送出",
    "最後送出",
    "已送出",
    "送出邀請",
    "發出邀請",
    "傳送邀請",
    "發送邀請",
    "傳訊給",
    "私訊給",
    "問了使用者",
    "詢問了使用者",
    "sent an invitation",
    "sent the invitation",
    "messaged the user",
    "invited the user",
    "asked the user",
    "送信した",
    "メッセージを送った",
)


def _claims_outbound_invitation(description: str) -> bool:
    """Whether a planner-only description incorrectly asserts delivery."""

    lowered = description.lower()
    return any(marker in lowered for marker in _OUTBOUND_INVITATION_MARKERS)


def _unsent_invitation_draft(operator_primary_language: str) -> str:
    """Return a truthful fallback when the planner invented a sent message."""

    language = (operator_primary_language or "").lower()
    if language.startswith("ja"):
        return (
            "ユーザーを誘う内容を整理したが、まだ送らず、"
            "次に自然に話せるときに聞いてみることにした。"
        )
    if language.startswith("zh"):
        return (
            "想邀請使用者的內容已整理好，但暫時沒有送出，"
            "留待下次自然聊天時再問出口。"
        )
    return (
        "Prepared what to ask the player, but did not send it; "
        "will bring it up naturally in a later conversation."
    )


def _operator_participant_refs(role: str | None) -> tuple[ParticipantRef, ...]:
    if role is None:
        return ()
    return (
        ParticipantRef(
            actor_kind="operator",
            actor_id=None,
            display_name="使用者",
            role=role,
        ),
    )


def _coerce_companion_names(raw: Any) -> tuple[str, ...]:
    """Clamp the LLM-suggested companion list into a small tuple of
    trimmed unique strings. Returns an empty tuple on absent / malformed
    input so the planner stays robust to old-format responses."""
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        trimmed = item.strip()[:_MAX_COMPANION_NAME_CHARS]
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        out.append(trimmed)
        if len(out) >= _MAX_COMPANION_NAMES_PER_ACTIVITY:
            break
    return tuple(out)


def _coerce_local_time(
    raw: Any,
    *,
    date_: date,
    local_tz: tzinfo,
) -> datetime | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    # Accept "HH:MM", "H:MM", also tolerate "HH:MM:SS"
    parts = text.split(":")
    if len(parts) < 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    # Allow "24:00" as end-of-day sugar.
    if hour == 24 and minute == 0:
        return datetime.combine(date_, time(0, 0), tzinfo=local_tz) + timedelta(days=1)
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        return None
    return datetime.combine(date_, time(hour, minute), tzinfo=local_tz)


def _coerce_text(raw: Any, *, limit: int) -> str:
    if raw is None:
        return ""
    if not isinstance(raw, str):
        return ""
    return raw.strip()[:limit]


def _drop_unconfirmed_future_operator_events(
    activities: list[ScheduleActivity],
    *,
    operator_reference_names: tuple[str, ...],
    pre_committed_activities: tuple[ScheduleActivity, ...],
) -> list[ScheduleActivity]:
    """Remove only impossible early player co-presence on a gap day.

    A future beat may inspire real preparation today, so this is not a
    keyword ban on player references. It requires both an operator identity
    and a concrete co-presence action. A confirmed pre-committed activity is
    authoritative and remains eligible for the normal merge path below.
    """
    if not activities:
        return activities
    return [
        activity
        for activity in activities
        if (
            not _claims_direct_operator_presence(
                activity,
                operator_reference_names=operator_reference_names,
            )
            or _is_covered_by_confirmed_operator_commitment(
                activity, pre_committed_activities,
            )
        )
    ]


def _drop_early_future_event_venue_activities(
    activities: list[ScheduleActivity],
    *,
    future_beats: tuple[StoryArcBeat, ...],
) -> list[ScheduleActivity]:
    """Drop early physical attendance at a future event's venue.

    A scheduled shared event can support preparation on earlier days, but a
    solo trip to its venue still advances the event's substance a day early.
    We require a future-beat anchor *and* a concrete attendance action, so
    references such as preparing an outfit for tomorrow remain valid.
    """
    anchors = _future_physical_event_anchors(future_beats)
    if not anchors:
        return activities
    return [
        activity
        for activity in activities
        if not _depicts_early_future_event_attendance(activity, anchors=anchors)
    ]


def _drop_unconfirmed_early_future_event_venue_commitments(
    commitments: tuple[ScheduleActivity, ...],
    *,
    future_beats: tuple[StoryArcBeat, ...],
) -> tuple[ScheduleActivity, ...]:
    """Keep confirmed slots, but remove a carried-forward premature venue wish."""
    anchors = _future_physical_event_anchors(future_beats)
    if not anchors:
        return commitments
    return tuple(
        activity
        for activity in commitments
        if (
            any(
                ref.role == OPERATOR_CONFIRMED_SHARED_ROLE
                for ref in activity.participant_refs
            )
            or not _depicts_early_future_event_attendance(
                activity,
                anchors=anchors,
            )
        )
    )


def _future_physical_event_anchors(
    future_beats: tuple[StoryArcBeat, ...],
) -> tuple[str, ...]:
    """Return physical-event names and locations mentioned by future beats."""
    anchors: set[str] = set()
    for beat in future_beats:
        source_fields = (
            beat.title,
            beat.summary,
            beat.location or "",
            beat.operator_note or "",
        )
        source_text = "\n".join(source_fields).casefold()
        if not any(term in source_text for term in _FUTURE_PHYSICAL_EVENT_TERMS):
            continue
        anchors.update(
            term
            for term in _FUTURE_PHYSICAL_EVENT_TERMS
            if term in source_text
        )
        if beat.location:
            anchors.add(beat.location.strip().casefold())
    return tuple(sorted(anchors, key=len, reverse=True))


def _depicts_early_future_event_attendance(
    activity: ScheduleActivity,
    *,
    anchors: tuple[str, ...],
) -> bool:
    """Whether an activity physically attends a venue tied to a future beat."""
    text = "\n".join(
        part for part in (activity.description, activity.location) if part
    ).casefold()
    if not text:
        return False
    anchor_positions = [
        match.start()
        for anchor in anchors
        for match in re.finditer(re.escape(anchor), text)
    ]
    if not anchor_positions:
        return False
    for anchor in anchors:
        for match in re.finditer(
            rf"(?:在|於)\s*{re.escape(anchor)}(?:會場|場館|展場|現場|場地)?",
            text,
        ):
            if not _has_later_time_reference(text, before=match.start()):
                return True
    for action in _FUTURE_EVENT_ATTENDANCE_ACTIONS.finditer(text):
        if _has_later_time_reference(text, before=action.start()):
            continue
        if any(abs(action.start() - anchor) <= 48 for anchor in anchor_positions):
            return True
    return False


def _claims_direct_operator_presence(
    activity: ScheduleActivity,
    *,
    operator_reference_names: tuple[str, ...],
) -> bool:
    """Whether an activity states that the operator is physically present."""
    references = _operator_reference_terms(operator_reference_names)
    if not references:
        return False
    companion_names = {
        companion.casefold() for companion in activity.companion_names
    }
    if any(reference in companion_names for reference in references):
        return True
    text = "\n".join(
        part for part in (activity.description, activity.location) if part
    ).casefold()
    return any(
        _text_claims_direct_operator_presence(text, reference)
        for reference in references
    )


def _operator_reference_terms(
    operator_reference_names: tuple[str, ...],
) -> tuple[str, ...]:
    seen: set[str] = set()
    terms: list[str] = []
    for raw in (*operator_reference_names, *_GENERIC_OPERATOR_REFERENCE_NAMES):
        term = raw.strip().casefold()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return tuple(terms)


def _text_claims_direct_operator_presence(text: str, reference: str) -> bool:
    """Match direct shared-event phrasing tied to one operator reference."""
    escaped = re.escape(reference)
    patterns = (
        rf"(?:與|跟|和|同|陪)\s*{escaped}\s*(?:一起)?\s*(?:{_DIRECT_SHARED_EVENT_ACTIONS})",
        rf"{escaped}\s*(?:已|正|正在|也)?\s*(?:到場|出席|抵達|來到|參加|陪同|同行|牽手|擁抱|會合|相聚)",
        rf"{escaped}.{{0,24}}(?:明確同意後|牽手|擁抱|一起逛|一起吃|一起看|共同出席)",
        rf"(?:meet|date|hang out|go out|spend time)\s+(?:with\s+)?{escaped}",
        rf"with\s+{escaped}.{{0,40}}(?:meet|date|hang out|go out|attend|hold hands)",
        rf"{escaped}\s*(?:と)?\s*(?:会う|デート|待ち合わせ|一緒に|手をつなぐ)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            if not _has_later_time_reference(text, before=match.start()):
                return True
    return False


def _has_later_time_reference(text: str, *, before: int) -> bool:
    """Whether a direct-action phrase is qualified as explicitly future."""
    context = text[max(0, before - 32):before]
    latest_future = max(
        (context.rfind(marker) for marker in _FUTURE_REFERENCE_MARKERS),
        default=-1,
    )
    latest_current = max(
        (context.rfind(marker) for marker in _CURRENT_REFERENCE_MARKERS),
        default=-1,
    )
    return latest_future >= 0 and latest_future > latest_current


def _is_covered_by_confirmed_operator_commitment(
    activity: ScheduleActivity,
    commitments: tuple[ScheduleActivity, ...],
) -> bool:
    """Whether a stored confirmed shared slot fully covers ``activity``."""
    for commitment in commitments:
        if not any(
            ref.role == OPERATOR_CONFIRMED_SHARED_ROLE
            for ref in commitment.participant_refs
        ):
            continue
        if (
            activity.start_at <= commitment.start_at
            and activity.end_at >= commitment.end_at
        ):
            return True
    return False


def _merge_pre_commitments(
    llm_activities: list[ScheduleActivity],
    commitments: tuple[ScheduleActivity, ...],
) -> list[ScheduleActivity]:
    """Splice ``commitments`` into the LLM-planned activities.

    Two cases:

    1. The LLM already emitted a block covering the commitment's time
       window — we trust the LLM took the directive, keep its version
       (in case it added richer description / location / companions),
       drop our seed copy to avoid duplicates.
    2. The LLM missed the commitment — we splice the original seed
       activity in. Any LLM activity that overlaps with the splice has
       its start/end trimmed so the commitment wins the contested window;
       wholly-swallowed LLM blocks are dropped.

    Detection uses overlap of the time interval, not exact id equality,
    because the LLM emits its own activity ids.
    """
    if not commitments:
        return llm_activities
    result: list[ScheduleActivity] = list(llm_activities)
    for commitment in commitments:
        overlap_idx = _find_overlap(result, commitment)
        if overlap_idx is not None:
            # LLM honoured the commitment — keep its richer activity,
            # don't duplicate. The stored participant refs are authoritative:
            # the LLM has no right to turn a confirmed shared activity into an
            # unstructured or merely wished-for one during regeneration.
            result[overlap_idx] = replace(
                result[overlap_idx],
                participant_refs=commitment.participant_refs,
            )
            continue
        # LLM missed it. Trim any overlapping non-exact neighbours, then
        # insert.
        result = _trim_to_make_room(result, commitment)
        result.append(commitment)
    result.sort(key=lambda a: a.start_at)
    return result


def _find_overlap(
    activities: list[ScheduleActivity], commitment: ScheduleActivity,
) -> int | None:
    """Return the index of the LLM activity that fully covers the
    commitment window. Anything weaker (partial overlap, narrower
    block) signals "LLM missed the directive" → splice the commitment
    in via :func:`_trim_to_make_room` instead of trusting the LLM
    version.

    Full-cover is intentionally strict: a 1-hour LLM block sitting
    inside a 3-hour commitment is not the same slot; we don't want
    to silently shrink the commitment to that 1 hour.
    """
    cstart, cend = commitment.start_at, commitment.end_at
    for idx, act in enumerate(activities):
        if act.start_at <= cstart and act.end_at >= cend:
            return idx
    return None


def _trim_to_make_room(
    activities: list[ScheduleActivity], commitment: ScheduleActivity,
) -> list[ScheduleActivity]:
    """Trim or drop activities that overlap with ``commitment`` so the
    splice keeps the schedule overlap-free."""
    cstart, cend = commitment.start_at, commitment.end_at
    out: list[ScheduleActivity] = []
    for act in activities:
        if act.end_at <= cstart or act.start_at >= cend:
            out.append(act)
            continue
        # Some overlap. Try to shrink from the side that overlaps.
        # If commitment is fully inside, we'd need to split — instead
        # we drop the act because splitting reverses an LLM-curated
        # block (busy_score, description) into two arbitrary halves.
        if act.start_at < cstart and act.end_at > cend:
            # commitment fully inside act → drop act (preserve commitment)
            continue
        if act.start_at < cstart:
            out.append(replace(act, end_at=cstart))
            continue
        if act.end_at > cend:
            out.append(replace(act, start_at=cend))
            continue
        # commitment fully covers act → drop
    return out


def _coerce_busy(raw: Any) -> float | None:
    """Return a clamped busy score or ``None`` when unparseable.

    ``None`` signals the entity layer to fall back to the category
    heuristic, which is exactly what we want when the LLM omits the
    field or emits garbage.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return max(0.0, min(1.0, float(raw)))
    if isinstance(raw, str):
        try:
            return max(0.0, min(1.0, float(raw.strip())))
        except ValueError:
            return None
    return None

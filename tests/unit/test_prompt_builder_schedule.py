"""Prompt builder renders schedule block."""

from __future__ import annotations

from datetime import datetime, timezone

from kokoro_link.domain.entities.character import Character
from kokoro_link.domain.entities.conversation import Conversation
from kokoro_link.domain.entities.schedule import (
    OPERATOR_CONFIRMED_LAPSED_ROLE,
    OPERATOR_INVITE_EXPIRED_ROLE,
    OPERATOR_INVITE_PENDING_ROLE,
    ScheduleActivity,
)
from kokoro_link.domain.value_objects.actor import ParticipantRef
from kokoro_link.domain.value_objects.character_state import CharacterState
from kokoro_link.infrastructure.prompt.default import (
    DefaultPromptContextBuilder,
    _render_pending_invites_block,
)


def _char() -> Character:
    return Character.create(
        name="Aki",
        summary="插畫家",
        personality=["溫柔"],
        interests=[],
        speaking_style="",
        boundaries=[],
        state=CharacterState(emotion="neutral", affection=50, fatigue=0, trust=50, energy=100),
    )


def _activity(hour: int, description: str, category: str = "work") -> ScheduleActivity:
    return ScheduleActivity.create(
        start_at=datetime(2026, 4, 18, hour, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 4, 18, hour + 1, 0, tzinfo=timezone.utc),
        description=description,
        category=category,
    )


def test_prompt_includes_current_activity() -> None:
    builder = DefaultPromptContextBuilder()
    character = _char()
    prompt = builder.build(
        character=character,
        conversation=Conversation.start(character_id=character.id),
        recent_messages=[],
        memories=[],
        pending_state=character.state,
        latest_user_message="你在做什麼？",
        current_activity=_activity(10, "在工作室畫草稿"),
        upcoming_activities=[_activity(14, "見客戶")],
    )
    assert "角色今日行程" in prompt
    assert "在工作室畫草稿" in prompt
    assert "見客戶" in prompt


def test_prompt_omits_schedule_block_when_no_activity() -> None:
    builder = DefaultPromptContextBuilder()
    character = _char()
    prompt = builder.build(
        character=character,
        conversation=Conversation.start(character_id=character.id),
        recent_messages=[],
        memories=[],
        pending_state=character.state,
        latest_user_message="嗨",
    )
    assert "角色今日行程" not in prompt


def test_prompt_handles_idle_current_with_upcoming() -> None:
    builder = DefaultPromptContextBuilder()
    character = _char()
    prompt = builder.build(
        character=character,
        conversation=Conversation.start(character_id=character.id),
        recent_messages=[],
        memories=[],
        pending_state=character.state,
        latest_user_message="嗨",
        current_activity=None,
        upcoming_activities=[_activity(14, "見客戶")],
    )
    assert "空檔" in prompt
    assert "見客戶" in prompt


def test_prompt_includes_completed_today_timeline_without_just_finished_duplicate() -> None:
    builder = DefaultPromptContextBuilder()
    character = _char()
    completed = _activity(9, "整理展覽草圖")
    just_finished = _activity(11, "收拾畫材")
    prompt = builder.build(
        character=character,
        conversation=Conversation.start(character_id=character.id),
        recent_messages=[],
        memories=[],
        pending_state=character.state,
        latest_user_message="你今天做了什麼？",
        just_finished_activity=just_finished,
        completed_today_activities=[completed, just_finished],
        now=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert "今天稍早已完成" in prompt
    assert "整理展覽草圖" in prompt
    assert prompt.count("收拾畫材") == 1


def test_prompt_includes_pending_invite_without_confirming_it() -> None:
    builder = DefaultPromptContextBuilder()
    character = _char()
    invite = ScheduleActivity.create(
        start_at=datetime(2026, 4, 18, 19, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 4, 18, 20, 0, tzinfo=timezone.utc),
        description="想約對方看電影",
        category="social",
        location="電影院",
        participant_refs=(
            ParticipantRef(
                actor_kind="operator",
                actor_id=None,
                display_name="使用者",
                role=OPERATOR_INVITE_PENDING_ROLE,
            ),
        ),
    )
    prompt = builder.build(
        character=character,
        conversation=Conversation.start(character_id=character.id),
        recent_messages=[],
        memories=[],
        pending_state=character.state,
        latest_user_message="嗨",
        pending_invite_activities=[invite],
        now=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert "尚未確認的邀請" in prompt
    assert "想約對方看電影" in prompt
    assert "對方還沒答應" in prompt
    assert "不要說成已約好" in prompt


def _invite(
    *,
    role: str,
    start_hour: int,
    end_hour: int,
    description: str = "想約對方去吃刨冰",
) -> ScheduleActivity:
    return ScheduleActivity.create(
        start_at=datetime(2026, 4, 18, start_hour, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 4, 18, end_hour, 0, tzinfo=timezone.utc),
        description=description,
        category="social",
        participant_refs=(
            ParticipantRef(
                actor_kind="operator",
                actor_id=None,
                display_name="使用者",
                role=role,
            ),
        ),
    )


def test_expired_invite_is_not_rendered_as_pending() -> None:
    """A commitment the sweep already retired must not come back as a
    「找機會問出口」 future plan (plan §2 P1c, 芊璃 刨冰 case)."""
    lines = _render_pending_invites_block(
        pending=[_invite(role=OPERATOR_INVITE_EXPIRED_ROLE, start_hour=19, end_hour=20)],
        local_tz=timezone.utc,
        now=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert lines == []


def test_lapsed_confirmed_plan_is_not_rendered_as_pending() -> None:
    lines = _render_pending_invites_block(
        pending=[_invite(role=OPERATOR_CONFIRMED_LAPSED_ROLE, start_hour=19, end_hour=20)],
        local_tz=timezone.utc,
        now=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert lines == []


def test_invite_whose_window_already_passed_is_not_rendered_as_future() -> None:
    """Structured time comparison only — no text inspection. An invite whose
    whole window is behind us can't be asked 「出口」 in the future tense."""
    lines = _render_pending_invites_block(
        pending=[_invite(role=OPERATOR_INVITE_PENDING_ROLE, start_hour=8, end_hour=9)],
        local_tz=timezone.utc,
        now=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert lines == []


def test_still_open_invite_survives_the_filter() -> None:
    lines = _render_pending_invites_block(
        pending=[_invite(role=OPERATOR_INVITE_PENDING_ROLE, start_hour=19, end_hour=20)],
        local_tz=timezone.utc,
        now=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert any("想約對方去吃刨冰" in line for line in lines)


def test_first_live_invite_wins_when_an_expired_one_leads_the_list() -> None:
    """The block renders a single invite; picking ``pending[0]`` blindly
    would let an expired entry suppress a live one."""
    lines = _render_pending_invites_block(
        pending=[
            _invite(
                role=OPERATOR_INVITE_EXPIRED_ROLE,
                start_hour=15,
                end_hour=16,
                description="過期的刨冰邀請",
            ),
            _invite(
                role=OPERATOR_INVITE_PENDING_ROLE,
                start_hour=19,
                end_hour=20,
                description="還沒問出口的電影邀請",
            ),
        ],
        local_tz=timezone.utc,
        now=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    body = "\n".join(lines)
    assert "還沒問出口的電影邀請" in body
    assert "過期的刨冰邀請" not in body


def test_pending_invite_block_without_clock_keeps_legacy_behaviour() -> None:
    """Replay/legacy callers pass no clock; the role filter still applies but
    the window comparison is skipped rather than guessed."""
    lines = _render_pending_invites_block(
        pending=[_invite(role=OPERATOR_INVITE_PENDING_ROLE, start_hour=8, end_hour=9)],
        local_tz=timezone.utc,
        now=None,
    )

    assert any("想約對方去吃刨冰" in line for line in lines)


def test_expired_invite_never_reaches_the_prompt() -> None:
    builder = DefaultPromptContextBuilder()
    character = _char()
    prompt = builder.build(
        character=character,
        conversation=Conversation.start(character_id=character.id),
        recent_messages=[],
        memories=[],
        pending_state=character.state,
        latest_user_message="嗨",
        pending_invite_activities=[
            _invite(
                role=OPERATOR_INVITE_EXPIRED_ROLE,
                start_hour=19,
                end_hour=20,
                description="陪使用者一起出門吃刨冰",
            ),
        ],
        now=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )

    # The footer's time-discipline rule names 「尚未確認的邀請」 as a section
    # to distrust, so match on the block's own body instead of the heading.
    assert "只是一個想問對方的念頭" not in prompt
    assert "陪使用者一起出門吃刨冰" not in prompt


# ---------------------------------------------------------------------------
# I-21: ongoing interaction in the schedule block
# ---------------------------------------------------------------------------

from datetime import timedelta  # noqa: E402

from kokoro_link.domain.value_objects.ongoing_interaction import (  # noqa: E402
    OngoingInteraction,
)


def _ongoing(*, started_during: bool, before=None) -> OngoingInteraction:
    t = datetime(2026, 4, 18, 9, 50, tzinfo=timezone.utc)
    return OngoingInteraction(
        last_exchange_at=t,
        minutes_since=4,
        streak_started_at=t - timedelta(minutes=20),
        activity_started_during_streak=started_during,
        activity_at_streak_start=before,
    )


def _prompt(current, ongoing, **extra) -> str:
    character = _char()
    conv = Conversation.start(character_id=character.id)
    return DefaultPromptContextBuilder().build(
        character=character,
        conversation=conv,
        recent_messages=[],
        memories=[],
        pending_state=character.state,
        latest_user_message="嗯",
        current_activity=current,
        upcoming_activities=[],
        ongoing_interaction=ongoing,
        **extra,
    ), character, conv


def test_none_ongoing_interaction_is_byte_identical() -> None:
    character = _char()
    conv = Conversation.start(character_id=character.id)
    kw = dict(
        character=character, conversation=conv, recent_messages=[],
        memories=[], pending_state=character.state, latest_user_message="嗯",
        current_activity=_activity(10, "洗澡"), upcoming_activities=[],
    )
    a = DefaultPromptContextBuilder().build(**kw)
    b = DefaultPromptContextBuilder().build(**kw, ongoing_interaction=None)
    assert a == b


def test_case_one_adds_one_line_and_softens_busy_hint() -> None:
    act = ScheduleActivity.create(
        start_at=datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 4, 18, 11, 0, tzinfo=timezone.utc),
        description="寫稿", category="work", busy_score=0.7,
    )
    prompt, _, _ = _prompt(act, _ongoing(started_during=False))
    assert "目前活動：" in prompt and "正在「寫稿」" in prompt
    assert "互動狀態：你和對方約 4 分鐘前還在對話" in prompt
    assert "依你的性格決定怎麼兼顧" in prompt
    assert "回覆保持簡潔" not in prompt


def test_case_two_presents_the_activity_as_a_plan() -> None:
    before = _activity(8, "一起吃飯", "social")
    cur = _activity(10, "洗澡", "hygiene")
    prompt, _, _ = _prompt(cur, _ongoing(started_during=True, before=before))
    assert "正在「洗澡」" not in prompt
    assert "忙碌程度" not in prompt
    assert "互動狀態：你和對方從" in prompt and "當時你正在「一起吃飯」" in prompt
    assert "行程上原定" in prompt and "「洗澡」" in prompt
    assert "唯一真實來源" not in prompt
    assert "延續對話裡最後的場景" in prompt


def test_shared_activity_with_player_renders_as_case_one() -> None:
    cur = ScheduleActivity.create(
        start_at=datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 4, 18, 11, 0, tzinfo=timezone.utc),
        description="一起看電影", category="social",
        participant_refs=(
            ParticipantRef(
                actor_kind="operator", actor_id="op", display_name="玩家",
                role=OPERATOR_INVITE_PENDING_ROLE,
            ),
        ),
    )
    from kokoro_link.domain.entities.schedule import has_live_operator_commitment
    assert has_live_operator_commitment(cur)
    prompt, _, _ = _prompt(cur, _ongoing(started_during=True))
    assert "正在「一起看電影」" in prompt
    assert "行程上原定" not in prompt


# ---------------------------------------------------------------------------
# I-21 phase 2 Part B: confirmed shared participation in the chat prompt
# ---------------------------------------------------------------------------

_SHARED_NOW = "這個時段是你和對方一起的活動，你們正一起進行中。"
_SHARED_RETURNING = "這個時段是你和對方約好一起的活動。對方中途可能離開過，現在出現了——"


def _operator_activity(role: str | None) -> ScheduleActivity:
    refs = ()
    if role is not None:
        refs = (
            ParticipantRef(
                actor_kind="operator", actor_id="op", display_name="玩家",
                role=role,
            ),
        )
    return ScheduleActivity.create(
        start_at=datetime(2026, 4, 18, 9, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 4, 18, 11, 0, tzinfo=timezone.utc),
        description="約會", category="social", participant_refs=refs,
    )


def test_confirmed_shared_mid_conversation_wording() -> None:
    from kokoro_link.domain.entities.schedule import OPERATOR_CONFIRMED_SHARED_ROLE
    prompt, _, _ = _prompt(
        _operator_activity(OPERATOR_CONFIRMED_SHARED_ROLE),
        _ongoing(started_during=False),
    )
    assert _SHARED_NOW in prompt
    assert _SHARED_RETURNING not in prompt
    assert prompt.index("目前活動：") < prompt.index(_SHARED_NOW)
    assert prompt.index("忙碌程度：") < prompt.index(_SHARED_NOW)
    assert prompt.index(_SHARED_NOW) < prompt.index("互動狀態：你和對方約")


def test_confirmed_shared_returning_wording() -> None:
    from kokoro_link.domain.entities.schedule import OPERATOR_CONFIRMED_SHARED_ROLE
    prompt, _, _ = _prompt(
        _operator_activity(OPERATOR_CONFIRMED_SHARED_ROLE), None,
    )
    assert _SHARED_RETURNING in prompt
    assert "不必追問他剛才去了哪裡" in prompt
    assert _SHARED_NOW not in prompt


def test_confirmed_shared_when_case_two_yields_does_not_apply() -> None:
    """Confirmed-shared never yields (live commitment), so it renders as case one."""
    from kokoro_link.domain.entities.schedule import OPERATOR_CONFIRMED_SHARED_ROLE
    prompt, _, _ = _prompt(
        _operator_activity(OPERATOR_CONFIRMED_SHARED_ROLE),
        _ongoing(started_during=True),
    )
    assert _SHARED_NOW in prompt
    assert "行程上原定" not in prompt


def test_non_confirmed_roles_render_without_shared_line() -> None:
    from kokoro_link.domain.entities.schedule import (
        OPERATOR_CONFIRMED_LAPSED_ROLE,
        OPERATOR_INVITE_EXPIRED_ROLE,
        OPERATOR_WISH_ROLE,
    )
    for role in (
        OPERATOR_INVITE_PENDING_ROLE,
        OPERATOR_WISH_ROLE,
        OPERATOR_INVITE_EXPIRED_ROLE,
        OPERATOR_CONFIRMED_LAPSED_ROLE,
        None,
    ):
        for ongoing in (None, _ongoing(started_during=False)):
            prompt, _, _ = _prompt(_operator_activity(role), ongoing)
            assert "一起的活動" not in prompt
            assert "約好一起的活動" not in prompt

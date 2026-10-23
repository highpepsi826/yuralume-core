from __future__ import annotations

from kokoro_link.application.services.messaging_dispatcher import (
    _persona_safe_for_account,
)
from kokoro_link.domain.entities.messaging_account import MessagingAccount
from kokoro_link.domain.value_objects.platform import Platform


def _account(*, senders: tuple[str, ...]) -> MessagingAccount:
    return MessagingAccount.create(
        character_id="char-A",
        platform=Platform.TELEGRAM,
        credentials={"bot_token": "token"},
        allowed_sender_refs=senders,
    )


def test_persona_enabled_only_for_single_allowed_sender() -> None:
    assert _persona_safe_for_account(_account(senders=("user-1",))) is True
    assert _persona_safe_for_account(_account(senders=())) is False
    assert _persona_safe_for_account(_account(senders=("user-1", "user-2"))) is False


def test_blank_allowlist_entries_do_not_count_as_senders() -> None:
    """The count is over *senders*, not over rows in the textarea.

    A player who leaves a trailing newline (or an empty line between two
    ids) must not flip an empty allowlist into "one sender", and a
    one-real-sender list with a stray blank must still be safe. Both
    directions matter: the first would disclose the owner's persona to
    anyone, the second would silence it for no reason.

    The filter is ``if ref`` — strictly-empty entries only. A
    whitespace-only entry *does* count (pinned below) and is left alone
    here: the design freezes this function's contract, and the player UI
    cannot produce one (``splitLines`` trims every line before the
    payload is built). Recorded as a follow-up rather than fixed in a
    diff that was told to read this file only.
    """
    assert _persona_safe_for_account(_account(senders=("",))) is False
    assert _persona_safe_for_account(_account(senders=("", "", ""))) is False
    assert _persona_safe_for_account(
        _account(senders=("user-1", "")),
    ) is True
    assert _persona_safe_for_account(
        _account(senders=("", "user-1", "")),
    ) is True
    assert _persona_safe_for_account(
        _account(senders=("user-1", "user-2", "")),
    ) is False
    # Current, unpinned-in-design behaviour: whitespace is not trimmed.
    assert _persona_safe_for_account(_account(senders=("  ",))) is True


def test_gate_module_and_dispatcher_share_one_answer() -> None:
    """``persona_disclosure_gate`` is the same rule, not a copy of it."""
    from kokoro_link.application.services.persona_disclosure_gate import (
        persona_safe_for_account,
    )

    for senders in ((), ("",), ("user-1",), ("user-1", "user-2")):
        assert (
            persona_safe_for_account(_account(senders=senders))
            == _persona_safe_for_account(_account(senders=senders))
        )

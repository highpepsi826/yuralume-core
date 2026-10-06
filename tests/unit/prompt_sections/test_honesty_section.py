"""Image-delivery guidance remains stable without auditing AIRP life."""

from __future__ import annotations

import pytest

from kokoro_link.infrastructure.prompt.sections.context import ToolsContext
from kokoro_link.infrastructure.prompt.sections.honesty import (
    SECTIONS,
)
from kokoro_link.infrastructure.prompt.sections.order import SECTION_ORDER

HONESTY_HEADING = "圖片交付界線"
NO_BROWSING_MARK = "這個環境沒有給你上網的能力"


class _ToolsOnlyContext:
    """Enough context for this section, and deliberately nothing more."""

    def __init__(self, character_tool_names: tuple[str, ...] | None) -> None:
        self.tools = ToolsContext(
            available_tools=(),
            tool_outcomes=(),
            forced_tool_name=None,
            character_tool_names=character_tool_names,
        )


def _render(character_tool_names: tuple[str, ...] | None) -> list[str]:
    (entry,) = SECTIONS
    return entry.render(_ToolsOnlyContext(character_tool_names))


def _text(character_tool_names: tuple[str, ...] | None) -> str:
    return "\n".join(_render(character_tool_names))


# --- the baseline is unconditional -----------------------------------


@pytest.mark.parametrize(
    "names", [None, (), ("web_search",), ("generate_image", "web_fetch")],
)
def test_the_baseline_discipline_renders_whatever_the_capability_set_is(
    names: tuple[str, ...] | None,
) -> None:
    # The point of hoisting this out of ``tools_block``: no tool offered
    # on this hop must never mean no honesty rule on this hop.
    assert HONESTY_HEADING in _text(names)


def test_real_image_delivery_requires_a_usable_image_attachment() -> None:
    body = _text(None)
    assert "這則訊息須有實際可交付的圖片附件" in body
    assert "工具成功但沒有圖片，或只有非圖片附件，都不算" in body
    assert "可以自然說稍後再傳" in body


def test_the_baseline_keeps_airp_device_actions_inside_the_shared_fiction() -> None:
    body = _text(None)
    assert "登入虛構遊戲" in body
    assert "按場景中的答錄機" in body
    assert "虛構照片、遊戲內照片" in body
    assert "未來傳圖的承諾" in body
    assert "不需要真實附件" in body
    assert "看影片、聊新聞、瀏覽網頁" in body
    assert "不需要工具證據" in body


def test_the_baseline_text_does_not_vary_with_the_offered_tools() -> None:
    """Constant bytes are what let this block sit in the cached prefix.

    Hop 0 offers the catalogue and hop 1 hides it; if this section's text
    moved between them it would break the DH5 stable prefix for every
    block behind it, on every tool-using turn.
    """
    assert _render(None) == _render(()) == _render(("web_search",))
    assert _render(("generate_image",)) == _render(("web_fetch", "web_search"))


@pytest.mark.parametrize(
    "names", [None, (), ("web_search",), ("generate_image",)],
)
def test_the_section_has_no_browsing_disclaimer_or_broad_completion_rule(
    names: tuple[str, ...] | None,
) -> None:
    body = _text(names)
    assert NO_BROWSING_MARK not in body
    assert "你打不開網頁" not in body
    assert "我沒辦法自己去查" not in body
    assert "我查到了" not in body
    assert "才算真的發生過" not in body


# --- placement -------------------------------------------------------


def test_the_section_sits_at_the_tail_of_the_cacheable_prefix() -> None:
    """Immediately after the tool rail, ahead of the per-turn zone.

    Pinned because the reason is invisible from the table: everything
    from ``presence_frame`` down is re-derived per turn, and parking a
    stable block behind them would cost the upstream prompt cache the
    whole run.
    """
    order = list(SECTION_ORDER)
    assert order[order.index("tools") + 1] == "honesty_discipline"
    assert order.index("honesty_discipline") < order.index("presence_frame")

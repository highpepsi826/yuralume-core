"""Per-tool guidance in the tool-use prompt block.

Regression cover for a specific failure: the block's judgements were
written for ``generate_image`` and rendered unconditionally, so a model
offered ``web_search`` read "沒有具體畫面可給 → 別叫工具" and declined
to search. AIRP narration and image attachment delivery have separate rules.
"""

from __future__ import annotations

from kokoro_link.contracts.prompt import PromptToolDescriptor
from kokoro_link.infrastructure.prompt.tools_block import render_tools_block


def _tool(name: str) -> PromptToolDescriptor:
    return PromptToolDescriptor(
        name=name,
        description=f"{name} 的用途說明",
        parameters_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )


def _render(*names: str, forced_tool_name: str | None = None) -> str:
    return "\n".join(
        render_tools_block(
            [_tool(name) for name in names], forced_tool_name=forced_tool_name,
        )
    )


def test_no_tools_renders_nothing() -> None:
    assert render_tools_block([]) == []


def test_image_guidance_is_absent_when_image_tool_is_not_offered() -> None:
    """The core regression: visual judgements must not reach a character
    that only has search, where they read as "don't call anything"."""
    block = _render("web_search")
    assert "具體畫面" not in block
    assert "生圖" not in block
    assert "自拍" not in block


def test_search_guidance_is_absent_when_search_tool_is_not_offered() -> None:
    block = _render("generate_image")
    assert "搜尋" not in block
    assert "我剛查了一下" not in block


def test_each_tool_gets_its_own_call_and_skip_triggers() -> None:
    block = _render("generate_image", "web_search")
    assert "該用 web_search 的時機：" in block
    assert "不必用 web_search 的時機：" in block
    assert "該用 generate_image 的時機：" in block
    assert "不必用 generate_image 的時機：" in block


def test_search_triggers_on_the_model_hedging() -> None:
    """"我記得好像" is the model telling itself it lacks a fact — the
    cheapest signal available that a lookup is warranted."""
    block = _render("web_search")
    assert "我記得好像" in block
    assert "查完再回答" in block


def test_search_skip_list_covers_companionship_not_difficulty() -> None:
    block = _render("web_search")
    assert "陪伴" in block
    assert "在你腦中，不在網路上" in block


def test_image_delivery_rule_is_shared_without_broad_tool_evidence_requirements() -> None:
    for names in (("web_search",), ("generate_image",), ("web_search", "generate_image")):
        block = _render(*names)
        assert "這則訊息須有可交付的圖片附件" in block
        assert "工具成功但沒有圖片，或只有非圖片附件，都不算" in block
        assert "沒有實際輸出工具 JSON，就不准" not in block
        assert "假裝你使用過任何工具" not in block
        assert "共同角色扮演裡的場景行動不需要工具" in block
        assert "劇情中的答錄機" in block
        assert "虛構照片、遊戲內照片" in block
        assert "影片、新聞與瀏覽敘述不需要工具證據" in block
        assert "外部資料、外部服務或產品資料" not in block


def test_search_narration_is_not_subject_to_broad_proof_prohibitions() -> None:
    block = _render("web_search")
    assert "我剛查了一下" not in block
    assert "我看到新聞說" not in block
    assert "憑空捏造消息" not in block


def test_image_stage_direction_rule_targets_real_attachment_delivery() -> None:
    block = _render("generate_image")
    assert "要透過產品交付真實圖片附件時" in block
    assert "旁白代替工具呼叫與圖片附件" in block
    assert "虛構照片、遊戲內照片與場景中的拍照可以照常敘述" in block


def test_staying_in_character_is_not_a_reason_to_skip_search() -> None:
    block = _render("web_search")
    assert "查詢過程對使用者是隱形的" in block


def test_unknown_tools_still_render_identity_and_contract() -> None:
    """A tool without a guidance entry degrades to name + description +
    schema; the shared rules still apply to it."""
    block = _render("some_new_tool")
    assert "### some_new_tool" in block
    assert "some_new_tool 的用途說明" in block
    assert '{"tool": "工具名稱", "args": {...}}' in block
    assert "該用 some_new_tool 的時機" not in block


def test_call_contract_states_one_tool_per_turn() -> None:
    block = _render("web_search", "generate_image")
    assert "一回合只能呼叫一個工具" in block


def test_forced_tool_directive_overrides_the_judgement_framing() -> None:
    block = _render("generate_image", forced_tool_name="generate_image")
    assert "本回合強制工具呼叫" in block
    assert "**這回合必須呼叫 `generate_image` 工具**" in block

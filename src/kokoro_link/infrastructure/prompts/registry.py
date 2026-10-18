"""Prompt Studio catalogue and template safety metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Template

from kokoro_link.infrastructure.prompts.loader import get_default_loader


@dataclass(frozen=True, slots=True)
class PromptTemplateDefinition:
    name: str
    title: str
    category: str
    player_editable: bool
    important: bool
    impact: str
    variables: tuple[str, ...]


_PLAYER_TEMPLATES = {
    "chat/instructions_footer_style": ("聊天回覆", "聊天語氣、篇幅與回覆方式。"),
    "feed/composer_style": ("LumeGram 貼文", "貼文文案、圖片與短影片選擇方式。"),
    "feed/comment_reply_style": ("LumeGram 留言回覆", "角色公開回覆留言的語氣。"),
    "feed/video_storyboard_style": ("短影片腳本", "短影片鏡頭與動作描述。"),
    "proactive/decider_instructions_style": ("主動訊息", "主動訊息的口吻與篇幅；不影響是否傳送的判斷。"),
}

_CATEGORY_IMPACTS = {
    "chat": "影響聊天回覆格式、狀態與時間事實的使用規則。",
    "feed": "影響貼文、留言或影片的輸出格式、媒體契約與事實限制。",
    "proactive": "影響主動聯繫的判斷、訊息契約與工具調用。",
    "memory": "影響長期記憶的擷取、整併與保留。",
    "persona": "影響玩家資訊的擷取、人格整併與探索計畫。",
    "schedule": "影響行程規劃、天氣調整與活動結束後的狀態。",
    "state": "影響角色狀態與當下意圖的更新。",
    "post_turn": "影響對話後的資料萃取、承諾及狀態更新。",
    "novelty_gate": "影響生成內容的品質判定與是否放行。",
    "prompt": "影響記憶及情境素材摘要，會改變後續模型所見資料。",
    "busy": "影響忙碌判斷、延後回覆及排定承諾的訊息生成。",
    "goal": "影響角色目標的審查與更新。",
    "shared": "影響角色知識、能力與安全邊界。",
    "register": "影響互動語域、稱呼及表達方式判斷。",
    "story": "影響故事規劃、節拍、場景與完成紀錄。",
    "dialogue": "影響歷史對話摘要及檢查點整併。",
    "tts": "影響語音合成前的文字翻譯。",
    "branching": "影響分支劇情的規劃、審查與潤飾。",
    "fusion": "影響融合劇情的規劃、演出與改編。",
    "character_card": "影響角色卡翻譯、正規化與匯入內容。",
    "arc_template": "影響故事模板的翻譯與結構。",
    "story_seed": "影響故事種子的翻譯與內容。",
    "operator_persona": "影響玩家資料如何呈現給生成模型。",
    "self_repetition": "影響重複表達的擷取及後續防重複判斷。",
    "memoir": "影響回憶錄的本地化與呈現。",
}


def _variables(raw: str) -> tuple[str, ...]:
    names: set[str] = set()
    for match in Template.pattern.finditer(raw):
        name = match.group("named") or match.group("braced")
        if name:
            names.add(name)
    return tuple(sorted(names))


def prompt_template_catalog() -> dict[str, PromptTemplateDefinition]:
    loader = get_default_loader()
    entries: dict[str, PromptTemplateDefinition] = {}
    for name in loader.template_names():
        raw = loader.raw_default(name)
        player = _PLAYER_TEMPLATES.get(name)
        important = player is None
        entries[name] = PromptTemplateDefinition(
            name=name,
            title=player[0] if player else name,
            category=name.split("/", 1)[0],
            player_editable=player is not None,
            important=important,
            impact=(
                player[1] if player else
                _CATEGORY_IMPACTS.get(name.split("/", 1)[0], "影響對應功能的生成規則與輸出契約。")
            ),
            variables=_variables(raw),
        )
    return entries


def template_default(name: str) -> str:
    return get_default_loader().raw_default(name)


def validate_template_override(name: str, content: object) -> str:
    catalog = prompt_template_catalog()
    definition = catalog.get(name)
    if definition is None:
        raise ValueError("unknown prompt template")
    if not isinstance(content, str):
        raise ValueError("prompt template content must be text")
    text = content.replace("\r\n", "\n").strip()
    if not text:
        return ""
    if len(text) > 24000:
        raise ValueError("prompt template content must be at most 24000 characters")
    if any(ord(char) < 32 and char not in "\n\t" for char in text):
        raise ValueError("prompt template content contains control characters")
    supplied = _variables(text)
    if supplied != definition.variables:
        raise ValueError(
            "prompt template variables must remain exactly: "
            + ", ".join(definition.variables or ("(none)",))
        )
    try:
        Template(text).substitute({name: "" for name in definition.variables})
    except ValueError as exc:
        raise ValueError(f"invalid prompt template syntax: {exc}") from None
    return text + "\n"

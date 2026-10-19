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
    "chat/instructions_footer_style": ("聊天回覆語氣", "聊天語氣、篇幅與回覆方式。"),
    "feed/composer_style": ("LumeGram 貼文語氣", "貼文文案、圖片與短影片選擇方式。"),
    "feed/comment_reply_style": ("LumeGram 留言回覆語氣", "角色公開回覆留言的語氣。"),
    "feed/video_storyboard_style": ("短影片鏡頭風格", "短影片鏡頭與動作描述。"),
    "proactive/decider_instructions_style": ("主動訊息語氣", "主動訊息的口吻與篇幅；不影響是否傳送的判斷。"),
}

_TEMPLATE_TITLES = {
    "arc_template/translator": "故事模板翻譯", "branching/critic": "分支劇情審查",
    "branching/planner_children": "分支劇情子節點規劃", "branching/planner_root": "分支劇情主節點規劃",
    "branching/polisher": "分支劇情潤飾", "busy/decider": "忙碌狀態判斷",
    "busy/follow_up_composer": "忙碌後續訊息", "busy/scheduled_promise_composer": "已排定承諾訊息",
    "character_card/sillytavern_normalizer": "SillyTavern 角色卡正規化", "character_card/translator": "角色卡翻譯",
    "chat/instructions_footer": "聊天核心回覆規則", "chat/register_guidance_base": "聊天語域基礎指引",
    "chat/register_guidance_neutral": "聊天中性語域指引", "chat/register_guidance_warm": "聊天溫暖語域指引",
    "dialogue/checkpoint_merge": "對話檢查點合併", "dialogue/summarizer": "對話摘要",
    "feed/comment_reply": "LumeGram 留言回覆規則", "feed/composer": "LumeGram 貼文生成規則",
    "feed/video_first_frame": "短影片首幀規劃", "feed/video_storyboard": "短影片分鏡規則",
    "fusion/adapt_operator_observer": "融合劇情操作者觀察改編", "fusion/adapt_operator_unchanged": "融合劇情操作者原樣改編",
    "fusion/adapt_operator_write_in": "融合劇情操作者寫入改編", "fusion/adapt_to_arc": "融合劇情轉故事線",
    "fusion/critic": "融合劇情審查", "fusion/planner": "融合劇情規劃", "fusion/polisher_spot": "融合劇情局部潤飾",
    "fusion/polisher_whole": "融合劇情全文潤飾", "fusion/writer": "融合劇情撰寫",
    "goal/reviewer": "角色目標審查", "memoir/localizer": "回憶錄本地化",
    "memory/consolidator": "長期記憶整併", "memory/extractor": "長期記憶擷取",
    "novelty_gate/gate": "回覆新鮮度品質檢查", "operator_persona/for_prompt_header": "玩家資訊提示標頭",
    "persona/consolidator": "玩家輪廓整併", "persona/curiosity_planner": "玩家探索規劃", "persona/extractor": "玩家資訊擷取",
    "post_turn/processor": "對話後處理", "proactive/decider_instructions": "主動訊息核心規則",
    "proactive/intention_judge": "主動訊息意圖判斷", "prompt/material_digest": "提示素材摘要",
    "register/profiler": "對話語域分析", "schedule/aftermath": "行程結束後處理",
    "schedule/planner": "行程規劃", "schedule/weather_drift": "天氣造成的行程調整",
    "self_repetition/extractor": "重複表達擷取", "shared/role_boundary": "角色知識與角色邊界",
    "state/current_intent_reconcile": "目前意圖校正", "state/idle_drift": "閒置狀態漂移",
    "story/arc_completion_memory": "故事線完成記憶", "story/arc_planner": "故事線規劃",
    "story/arc_series_continuation_draft": "故事系列續寫草稿", "story/beat_rechecker": "故事節拍檢查",
    "story/beat_scene_writer": "故事節拍場景撰寫", "story/expander_scene": "故事場景擴寫",
    "story/expander_seed": "故事種子擴寫", "story/scene_chips": "故事場景選項",
    "story/scene_closer": "故事場景收尾", "story/scene_opener": "故事場景開場",
    "story/season_decider": "故事季節判定", "story_seed/translator": "故事種子翻譯",
    "tts/translator": "語音文字翻譯",
}

_CATEGORY_TITLES = {
    "arc_template": "故事模板", "branching": "分支劇情", "busy": "忙碌處理",
    "character_card": "角色卡", "chat": "聊天", "dialogue": "對話整理",
    "feed": "LumeGram", "fusion": "融合劇情", "goal": "角色目標",
    "memoir": "回憶錄", "memory": "長期記憶", "novelty_gate": "新鮮度檢查",
    "operator_persona": "玩家輪廓", "persona": "玩家資訊", "post_turn": "對話後處理",
    "proactive": "主動訊息", "prompt": "提示素材", "register": "語域",
    "schedule": "行程", "self_repetition": "重複表達", "shared": "共用規則",
    "state": "角色狀態", "story": "故事", "story_seed": "故事種子", "tts": "語音",
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
        category_key = name.split("/", 1)[0]
        important = player is None
        entries[name] = PromptTemplateDefinition(
            name=name,
            title=f"{name}（{player[0] if player else _TEMPLATE_TITLES.get(name, '系統提示模板')}）",
            category=f"{category_key}（{_CATEGORY_TITLES.get(category_key, '系統功能')}）",
            player_editable=player is not None,
            important=important,
            impact=(
                player[1] if player else
                _CATEGORY_IMPACTS.get(category_key, "影響對應功能的生成規則與輸出契約。")
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

"""Stable image-delivery guidance, including the final hop without tools.

The legacy section identifier is retained for prompt ordering compatibility.
AIRP life and shared scenes do not require evidence of external tool use.
"""

from typing import Final

from kokoro_link.infrastructure.prompt.sections.context import (
    PromptSectionContext,
)
from kokoro_link.infrastructure.prompt.sections.registry import (
    PromptSection,
    section,
)

_IMAGE_DELIVERY_LINES: Final[tuple[str, ...]] = (
    "",
    "圖片交付界線（只適用於透過產品傳給玩家的真實圖片附件）：",
    "- 要說「圖片已傳給你」「已附上」或以台詞表示正在交付真實圖片，"
    "這則訊息須有實際可交付的圖片附件；工具成功但沒有圖片，或只有非圖片附件，都不算。"
    "還沒有圖片時，可以自然說稍後再傳或說明圖片尚未準備好。",
    "- 你和對方共享的角色扮演照常延續：虛構照片、遊戲內照片、"
    "場景中拍照或交換照片，以及未來傳圖的承諾，都可以用文字敘述，不需要真實附件。",
    "- 角色生活裡看影片、聊新聞、瀏覽網頁、登入虛構遊戲、按場景中的答錄機，"
    "都可自然敘述，不需要工具證據；對方傳來的圖片與文字也可以直接引用或評論。",
)


def _honesty_discipline(_ctx: PromptSectionContext) -> list[str]:
    return list(_IMAGE_DELIVERY_LINES)


SECTIONS: tuple[PromptSection, ...] = (
    section("honesty_discipline", _honesty_discipline),
)

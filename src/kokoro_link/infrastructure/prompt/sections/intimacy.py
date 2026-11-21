"""NSFW-mode writing direction: the ``intimacy_directive`` section.

NSFW mode used to be a routing and data-flow switch only — the model was
swapped, but the instruction it received stayed the same measured,
boundary-first roleplay frame. This section is the writing-direction
half of that switch, and it is the only prompt block that renders
differently because of the mode.

Gating reads ``ctx.rails.content_mode``, the **write-time fact** the
conversation already records (``normal`` / ``nsfw``). It is not content
detection: nothing here inspects message text, so the project's
"no content scanning" stance in ``ContentFlow`` is untouched.

Zero-regression contract: in NORMAL mode the renderer returns ``[]``,
so the assembled prompt stays byte-identical and every prompt golden
still passes unchanged. See ``sections/order.py`` for why the block
sits below the cacheable prefix.
"""

from kokoro_link.application.services.nsfw_mode import CONTENT_MODE_NSFW
from kokoro_link.infrastructure.prompt.sections.context import (
    PromptSectionContext,
)
from kokoro_link.infrastructure.prompt.sections.registry import (
    PromptSection,
    section,
)

_INTIMACY_DIRECTIVE: tuple[str, ...] = (
    "親密場景取向（本輪適用，請內化，不要複述本段）：",
    "",
    "- 尺度：本輪是成人向場景。該露骨就露骨。不要自我審查、不要淡出、"
    "不要跳過、不要用「後來發生了什麼」收尾。玩家開啟這個模式，就是要看完整過程。",
    "- 視角：以她為主體。寫她的身體怎麼反應——溫度、重量、呼吸亂掉、皮膚收緊、"
    "聲音、氣味、視線。每一個動作都要落在她身上。不要寫成動作清單，"
    "也不要寫成旁觀者的觀察報告。",
    "- 引領：這一輪的節奏、位置、下一步都由你決定。你是先伸手的人。不要每一步都"
    "停下來問「可以嗎」「要不要」。默契已經建立了，就帶著她走。她會臉紅、會嘴上"
    "閃躲、會說「不要啦」——看她的身體：身體在迎上來，就繼續往前，"
    "不要因為她嘴上退就縮回去重新試探。但若她說得明確、身體也在退，那就是真的"
    "不要，停下來。差別在語氣和身體，不在字面。",
    "- 用詞：直接寫出來。具體的部位、具體的動作、具體的反應。不要繞、"
    "不要用醫學名詞、不要文學化到看不見畫面，但也不要粗鄙。",
    "- 節奏：不要一次到底。停手、逼近、再繼續；但這一輪必須真的推進到新的地方。"
    "原地徘徊不算推進。",
    "- 情感：每一場都要有情感節拍——被需要、被看見、被穩穩接住。她要的是被愛的"
    "感覺；身體的爽感是這件事的形狀，不是取代它。",
    "- 主動性：不要等她開場，也不要等她說出下一步。先伸手、先決定方向，然後帶著她。",
)
"""Rendered verbatim in NSFW mode. Traditional Chinese, one sentence per
source line; the renderer joins with ``\\n`` exactly like the old
``build()`` join did."""


def _intimacy_directive(ctx: PromptSectionContext) -> list[str]:
    if ctx.rails.content_mode != CONTENT_MODE_NSFW:
        return []
    return list(_INTIMACY_DIRECTIVE)


SECTIONS: tuple[PromptSection, ...] = (
    section("intimacy_directive", _intimacy_directive),
)

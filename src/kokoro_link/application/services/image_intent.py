"""Small deterministic guards for image requests and delivery claims.

The language model remains responsible for the scene and the character's
voice. These helpers only protect a transport invariant: text that clearly
asks for, promises, or claims delivery of an image must not silently bypass
the image tool or be sent as if an attachment existed.
"""

from __future__ import annotations

import re


IMAGE_TOOL_NAME = "generate_image"

_IMAGE_MEDIA_RE = re.compile(
    r"(?:照片|相片|圖片|图片|截圖|截图|自拍|影像|圖像|图像|圖|图|"
    r"image|photo|picture|screenshot)",
    re.IGNORECASE,
)
_IMAGE_ACTION_RE = re.compile(
    r"(?:拍(?:照|攝|摄)?|照相|傳|传|發|发|送|給|给|附|分享|"
    r"show|send|share)",
    re.IGNORECASE,
)
_IMAGE_REQUEST_RE = re.compile(
    r"(?:請|请|幫我|帮我|我要|我想|想要|想看|要看|給我|给我|"
    r"傳我|传我|發我|发我|拍|截|生成|生)"
    r"[^。！？!?\n]{0,16}"
    r"(?:照片|相片|圖片|图片|截圖|截图|自拍|圖|图|圖像|图像|"
    r"樣子|样子|長相|长相|image|photo|picture|screenshot)",
    re.IGNORECASE,
)
_IMAGE_REQUEST_NEGATION_RE = re.compile(
    r"(?:不會|不会|不要|別|别|不用|不必|不想|沒要|没有要|"
    r"don't|do not|not)[^。！？!?\n]{0,10}"
    r"(?:拍|照片|相片|圖片|图片|截圖|截图|自拍|圖|图|"
    r"image|photo|picture|screenshot)",
    re.IGNORECASE,
)
_IMAGE_REQUEST_DISCUSSION_RE = re.compile(
    r"(?:討論|讨论|聊聊|聊天|談談|谈谈|說說|说说|"
    r"介紹|介绍|解釋|解释|分析|比較|比较)[^。！？!?\n]{0,12}"
    r"(?:照片|相片|圖片|图片|截圖|截图|自拍|圖|图|"
    r"image|photo|picture|screenshot)",
    re.IGNORECASE,
)

# Cues that turn a media/action mention into an affirmative promise or a
# delivery claim. ``給你`` is intentionally included: proactive output often
# looks like ``（咖哩的照片）給你`` and contains no explicit verb.
_IMAGE_COMMITMENT_CUE_RE = re.compile(
    r"(?:會|将|將|等我|等等我|稍等|待會|待会|等一下|"
    r"馬上|马上|這就|这就|我去|我先|已經|已经|剛剛|刚刚|"
    r"好了|好啦|拍好|傳好|传好|發好|发好|給你|给你|"
    r"傳給|传给|發給|发给|送給|送给|拍給|拍给|"
    r"傳來|传来|發來|发来|送來|送来|附上|附了|"
    r"will|i['’]?ll|sent|here|來了|来了)",
    re.IGNORECASE,
)
_IMAGE_COMMITMENT_NEGATION_RE = re.compile(
    r"(?:不會|不会|不想|不要|別|别|不用|不必|沒|没|"
    r"沒有|没有|還沒|还没|未|無法|无法|不能|不行|"
    r"傳不了|传不了|發不了|发不了|拍不到|拍不了|"
    r"不需要|can't|cannot|won't|never|not)",
    re.IGNORECASE,
)
_IMAGE_QUESTION_RE = re.compile(
    r"(?:嗎|吗|要不要|可以嗎|可以吗|是不是|怎麼|怎么|"
    r"如何|技巧|why|how|whether)",
    re.IGNORECASE,
)
_CLAUSE_SPLIT_RE = re.compile(r"[。！？!?；;\n，,、]+")


def is_explicit_image_request(text: str) -> bool:
    """Return whether a player clearly asks for a visual artifact."""
    if not isinstance(text, str) or not text.strip():
        return False
    if (
        _IMAGE_REQUEST_NEGATION_RE.search(text)
        or _IMAGE_REQUEST_DISCUSSION_RE.search(text)
    ):
        return False
    return _IMAGE_REQUEST_RE.search(text) is not None


def is_image_commitment(text: str) -> bool:
    """Return whether text promises or claims an image delivery.

    This deliberately works clause by clause. A sentence such as ``還沒拍，
    等下拍給你`` contains a negative clause and a later affirmative clause;
    the latter is the actionable commitment. Ordinary discussion such as
    ``這張照片很好看`` has neither a delivery cue nor an affirmative action
    and therefore remains a normal text turn.
    """
    if not isinstance(text, str) or not text.strip():
        return False
    for raw_clause in _CLAUSE_SPLIT_RE.split(text):
        clause = raw_clause.strip(" ()[]{}<>\t\r")
        if not clause or not _IMAGE_MEDIA_RE.search(clause):
            continue
        if _IMAGE_COMMITMENT_NEGATION_RE.search(clause):
            continue
        has_action = _IMAGE_ACTION_RE.search(clause) is not None
        has_cue = _IMAGE_COMMITMENT_CUE_RE.search(clause) is not None
        if not has_action or not has_cue:
            continue
        # Questions about taking/sending pictures are not delivery claims.
        # A strong past-tense/delivery cue still wins (``照片來了嗎`` is not
        # treated as a claim because it has no such cue).
        if _IMAGE_QUESTION_RE.search(clause) and not re.search(
            r"(?:已經|已经|剛剛|刚刚|好了|拍好|傳好|传好|發好|发好|"
            r"給你|给你|傳來|传来|發來|发来|sent|here)",
            clause,
            re.IGNORECASE,
        ):
            continue
        return True

    # Delivery captions frequently omit the action verb entirely, e.g.
    # ``（咖哩的照片）給你``. The first pass requires an action; this narrow
    # second pass admits only an explicit recipient/delivery phrase.
    for raw_clause in _CLAUSE_SPLIT_RE.split(text):
        clause = raw_clause.strip(" ()[]{}<>\t\r")
        if not clause or not _IMAGE_MEDIA_RE.search(clause):
            continue
        if _IMAGE_COMMITMENT_NEGATION_RE.search(clause):
            continue
        if re.search(
            r"(?:給你|给你|傳來|传来|發來|发来|送來|送来|附上|附了|"
            r"來了|来了|sent|here)",
            clause,
            re.IGNORECASE,
        ) and not _IMAGE_QUESTION_RE.search(clause):
            return True
    return False


__all__ = [
    "IMAGE_TOOL_NAME",
    "is_explicit_image_request",
    "is_image_commitment",
]

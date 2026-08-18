from kokoro_link.application.services.image_intent import (
    is_explicit_image_request,
    is_image_commitment,
)


def test_image_commitment_detects_photo_promise_and_caption_delivery() -> None:
    assert is_image_commitment("我會拍咖哩照片給你")
    assert is_image_commitment("（咖哩的照片）給你，這次真的沒焦了")


def test_image_commitment_ignores_negation_questions_and_discussion() -> None:
    assert not is_image_commitment("我不會拍照片給你")
    assert not is_image_commitment("照片還沒拍好")
    assert not is_image_commitment("你有照片給我嗎")
    assert not is_image_commitment("這張照片很好看")


def test_explicit_request_keeps_discussion_and_negation_as_normal_chat() -> None:
    assert is_explicit_image_request("我要看咖哩照片")
    assert not is_explicit_image_request("我不會拍照片給你")
    assert not is_explicit_image_request("我想跟你討論照片")

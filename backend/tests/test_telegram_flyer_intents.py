import pytest

from app.integrations.telegram.edit_intents import FlyerEditKind, parse_flyer_edit_intent


@pytest.mark.parametrize(
    ("text", "kind", "reference", "value"),
    [
        ("Coca Cola'yı daha büyük yap", FlyerEditKind.CHANGE_HERO_PRODUCT, "Coca Cola", None),
        ("Coca Cola'yı öne çıkar", FlyerEditKind.CHANGE_HERO_PRODUCT, "Coca Cola", None),
        ("Coca Cola'nın vurgusunu azalt", FlyerEditKind.REDUCE_PRODUCT_EMPHASIS, "Coca Cola", None),
        ("Cips'i kaldır", FlyerEditKind.REMOVE_PRODUCT, "Cips", None),
        ("Eti ürünlerini aynı gruba al", FlyerEditKind.REGROUP_PRODUCTS, "Eti", None),
        ("Benzer ürünleri grupla", FlyerEditKind.REGROUP_PRODUCTS, None, None),
        ("Bu çok kalabalık olmuş, sadeleştir", FlyerEditKind.ADJUST_VISUAL_DENSITY, None, "simpler"),
        ("Daha dikkat çekici yap", FlyerEditKind.ADJUST_VISUAL_DENSITY, None, "eye_catching"),
        ("Başlığı daha dikkat çekici yap", FlyerEditKind.ADJUST_VISUAL_DENSITY, None, "eye_catching"),
        ("Fiyatları daha görünür yap", FlyerEditKind.INCREASE_PRICE_PROMINENCE, None, "high"),
        ("Başlığı değiştir: Hafta Sonu Fırsatları", FlyerEditKind.SET_TITLE, None, "Hafta Sonu Fırsatları"),
        ("Yeniden oluştur", FlyerEditKind.RERENDER_CURRENT_CAMPAIGN, None, None),
        ("PDF gönder", FlyerEditKind.CHANGE_FORMAT, None, "pdf"),
        ("Instagram hikaye formatı", FlyerEditKind.CHANGE_FORMAT, None, "instagram_story"),
    ],
)
def test_parse_flyer_edit_intent_maps_bounded_commands(text, kind, reference, value) -> None:
    intent = parse_flyer_edit_intent(text)

    assert intent is not None
    assert intent.kind == kind
    assert intent.product_reference == reference
    assert intent.value == value


def test_parse_flyer_edit_intent_rejects_unknown_or_commercial_fact_changes() -> None:
    assert parse_flyer_edit_intent("Bunu daha sanatsal ve üç boyutlu yap") is None
    assert parse_flyer_edit_intent("Coca Cola fiyatını 1,99 yap") is None

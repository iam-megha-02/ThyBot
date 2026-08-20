import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from add_thyroid_impact import tag_medication_timing_relevance, tag_thyroid_impact


def test_cruciferous_vegetable_tagged_goitrogenic():
    assert "Goitrogenic" in tag_thyroid_impact("Cabbage Sabzi")


def test_millet_tagged_goitrogenic():
    # Notable specifically for an India-focused dataset — millets
    # (bajra, jowar, ragi) are a documented goitrogen source and a
    # dietary staple, unlike the more commonly-cited cabbage/soy.
    assert "Goitrogenic" in tag_thyroid_impact("Bajra Roti")
    assert "Goitrogenic" in tag_thyroid_impact("Ragi Dosa")


def test_soy_tagged_goitrogenic():
    assert "Goitrogenic" in tag_thyroid_impact("Soya Chunks Curry")


def test_iodine_source_tagged_supportive():
    assert "Supportive" in tag_thyroid_impact("Fish Curry")
    assert "Supportive" in tag_thyroid_impact("Boiled Egg")
    assert "Supportive" in tag_thyroid_impact("Paneer Butter Masala")


def test_selenium_source_tagged_supportive():
    assert "Supportive" in tag_thyroid_impact("Roasted Almonds")


def test_unrelated_dish_tagged_neutral():
    assert "Neutral" in tag_thyroid_impact("Plain Rice")


def test_high_calcium_dish_flagged_for_medication_timing():
    note = tag_medication_timing_relevance(calcium_mg=150, iron_mg=0.5)
    assert "4+ hours" in note
    assert "calcium" in note


def test_high_iron_dish_flagged_for_medication_timing():
    note = tag_medication_timing_relevance(calcium_mg=10, iron_mg=5)
    assert "4+ hours" in note
    assert "iron" in note


def test_dish_with_both_flags_mentions_both_reasons():
    note = tag_medication_timing_relevance(calcium_mg=150, iron_mg=5)
    assert "calcium" in note and "iron" in note


def test_low_calcium_and_iron_dish_has_no_timing_concern():
    note = tag_medication_timing_relevance(calcium_mg=10, iron_mg=0.5)
    assert note == "No known timing concern"

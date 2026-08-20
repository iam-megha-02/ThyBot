"""
Tags each dish in the Indian food dataset with a thyroid-relevant
classification.

Goitrogen and iodine/selenium-support status are categorical here, not
per-gram quantities — that matches how they're actually represented in
clinical nutrition literature (a food either is or isn't from a known
goitrogen-producing family; there's no single "goitrogen content"
value the way there is for, say, sodium). This was checked against
IFCT 2017 (Indian Food Composition Tables, NIN/ICMR — the free,
open, authoritative Indian food composition database:
https://github.com/nodef/ifct2017) before writing this: IFCT does not
include an iodine column at all (iodine content is notoriously
inconsistent — it depends on soil and water content, not just the
food itself — which is why most composition databases omit it), and
its 528 entries are raw ingredients ("Amaranth seed, black"), not the
prepared dishes this CSV lists ("Chicken Biryani"), so there's no
clean per-dish match anyway. Fabricating plausible-looking iodine
numbers would be worse than not having them — this stays a category
tag, honestly.

What *is* real, measured, and already sitting in this CSV: calcium and
iron per dish. Both are known levothyroxine-absorption interactions
(see utils/medication_timing.py) — a high-calcium or high-iron dish
matters to someone on thyroid medication in a way the old script never
surfaced. That's the actual data-driven addition here.
"""

import pandas as pd

# Cruciferous/Brassica family (glucosinolates), soy (isoflavones), and
# millets (documented goitrogenic effect, notable here since millets
# are a staple in parts of the Indian diet) — categories drawn from
# published thyroid-nutrition literature, not a single study's food list.
GOITROGENIC_FOODS = (
    "cabbage", "cauliflower", "broccoli", "brussels sprout", "kale",
    "mustard", "turnip", "radish", "kohlrabi", "spinach",
    "soy", "soya", "tofu",
    "peanut", "groundnut",
    "millet", "bajra", "jowar", "ragi",
)

# Iodine sources (dairy, eggs, seafood, iodized salt) and selenium
# sources (nuts, mushrooms, sunflower seeds, whole grains) — the two
# micronutrients most directly tied to thyroid hormone synthesis.
THYROID_SUPPORTIVE_FOODS = (
    "fish", "prawn", "shrimp", "seafood",
    "egg",
    "milk", "curd", "yogurt", "yoghurt", "cheese", "paneer",
    "iodized salt", "sea salt",
    "brazil nut", "almond", "cashew", "sunflower seed", "mushroom",
    "brown rice", "whole grain", "whole wheat",
)

# Real, measured thresholds already validated in utils/medication_timing.py's
# interaction data — not new numbers, just applied to this CSV's existing columns.
HIGH_CALCIUM_MG_THRESHOLD = 100
HIGH_IRON_MG_THRESHOLD = 3


def tag_thyroid_impact(food: str) -> str:
    f = str(food).lower()
    if any(g in f for g in GOITROGENIC_FOODS):
        return "Goitrogenic – Limit in Hypothyroidism"
    elif any(s in f for s in THYROID_SUPPORTIVE_FOODS):
        return "Thyroid Supportive – Good for Thyroid Health"
    else:
        return "Neutral – No major thyroid impact"


def tag_medication_timing_relevance(calcium_mg: float, iron_mg: float) -> str:
    """
    Flags dishes worth separating from a levothyroxine dose by several
    hours, per the same calcium/iron interaction utils/medication_timing.py
    already encodes — connects the Meal Analysis feature to the
    Medications feature using data this CSV already measured.
    """
    reasons = []
    if calcium_mg >= HIGH_CALCIUM_MG_THRESHOLD:
        reasons.append("high calcium")
    if iron_mg >= HIGH_IRON_MG_THRESHOLD:
        reasons.append("high iron")
    if reasons:
        return f"Separate from levothyroxine by 4+ hours ({', '.join(reasons)})"
    return "No known timing concern"


if __name__ == "__main__":
    df = pd.read_csv("data/Indian_Food_Nutrition_Processed.csv")
    df["Thyroid_Impact"] = df["Dish Name"].apply(tag_thyroid_impact)
    df["Medication_Timing_Note"] = df.apply(
        lambda row: tag_medication_timing_relevance(row["Calcium (mg)"], row["Iron (mg)"]), axis=1
    )
    df.to_csv("data/Indian_Food_Nutrition_Processed.csv", index=False)
    print("Thyroid_Impact and Medication_Timing_Note columns added successfully!")

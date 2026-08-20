"""
Deterministic levothyroxine timing-interaction lookup.

Not an LLM call: the whole point is that timing guidance for a thyroid
medication should come from a fixed, reviewable table, not a model
improvising nutrition advice per request.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class InteractionSeverity(Enum):
    SEPARATE_STRICT = "separate_strict"
    SEPARATE_CAUTION = "separate_caution"
    NO_KNOWN_INTERACTION = "no_known_interaction"


@dataclass(frozen=True)
class TimingRule:
    aliases: tuple
    min_hours_apart: Optional[float]
    guidance: str
    severity: InteractionSeverity
    source_note: str


LEVOTHYROXINE_TIMING_RULES: tuple = (
    TimingRule(
        aliases=("calcium", "calcium carbonate", "calcium citrate", "tums", "calcium supplement"),
        min_hours_apart=4.0,
        guidance=(
            "Calcium significantly reduces levothyroxine absorption. Take "
            "levothyroxine at least 4 hours apart from any calcium supplement "
            "or calcium-fortified food."
        ),
        severity=InteractionSeverity.SEPARATE_STRICT,
        source_note="Well-established pharmacokinetic interaction, consistent across levothyroxine prescribing information.",
    ),
    TimingRule(
        aliases=("iron", "ferrous sulfate", "iron supplement", "multivitamin with iron"),
        min_hours_apart=4.0,
        guidance="Iron binds levothyroxine in the gut and reduces absorption. Separate doses by at least 4 hours.",
        severity=InteractionSeverity.SEPARATE_STRICT,
        source_note="Well-established pharmacokinetic interaction, consistent across levothyroxine prescribing information.",
    ),
    TimingRule(
        aliases=("antacid", "aluminum hydroxide", "magnesium hydroxide", "milk of magnesia"),
        min_hours_apart=4.0,
        guidance="Aluminum- and magnesium-containing antacids reduce levothyroxine absorption. Separate by at least 4 hours.",
        severity=InteractionSeverity.SEPARATE_STRICT,
        source_note="Well-established pharmacokinetic interaction.",
    ),
    TimingRule(
        aliases=("cholestyramine", "colestipol", "bile acid sequestrant"),
        min_hours_apart=5.0,
        guidance="Bile acid sequestrants strongly bind levothyroxine. Separate by at least 4-5 hours.",
        severity=InteractionSeverity.SEPARATE_STRICT,
        source_note="One of the stronger known binding interactions.",
    ),
    TimingRule(
        aliases=("coffee", "caffeine", "espresso"),
        min_hours_apart=0.5,
        guidance=(
            "Coffee can reduce levothyroxine absorption if taken too close "
            "together. Wait at least 30-60 minutes after your dose before "
            "drinking coffee."
        ),
        severity=InteractionSeverity.SEPARATE_CAUTION,
        source_note="Reported to reduce absorption; magnitude varies by individual.",
    ),
    TimingRule(
        aliases=("soy", "soybean", "soy milk", "tofu"),
        min_hours_apart=4.0,
        guidance="Soy products can reduce levothyroxine absorption. Where possible, separate intake by several hours.",
        severity=InteractionSeverity.SEPARATE_CAUTION,
        source_note="Evidence is more mixed than calcium/iron, but spacing is commonly advised.",
    ),
    TimingRule(
        aliases=("fiber", "high-fiber", "bran", "psyllium"),
        min_hours_apart=4.0,
        guidance="High-fiber foods and supplements may reduce levothyroxine absorption. Where possible, separate by several hours.",
        severity=InteractionSeverity.SEPARATE_CAUTION,
        source_note="Evidence is more mixed; spacing is a common precaution.",
    ),
    TimingRule(
        aliases=("ppi", "omeprazole", "esomeprazole", "pantoprazole", "proton pump inhibitor"),
        min_hours_apart=None,
        guidance=(
            "Proton pump inhibitors reduce stomach acid, which can lower "
            "levothyroxine absorption over time. There's no simple spacing "
            "window for this one — ask your doctor whether your thyroid "
            "levels should be monitored more closely while on a PPI."
        ),
        severity=InteractionSeverity.SEPARATE_CAUTION,
        source_note="Mechanism is acid-dependent absorption, not a direct binding interaction — spacing alone doesn't resolve it.",
    ),
)

DISCLAIMER = (
    "This is general educational information about known levothyroxine "
    "timing interactions, not medical advice. It doesn't account for your "
    "specific dose, other conditions, or full medication list. Confirm any "
    "changes with your doctor or pharmacist."
)


@dataclass(frozen=True)
class TimingGuidance:
    item: str
    matched: bool
    min_hours_apart: Optional[float]
    guidance: str
    severity: InteractionSeverity
    source_note: str


def _find_rule(item: str) -> Optional[TimingRule]:
    for rule in LEVOTHYROXINE_TIMING_RULES:
        if any(alias in item for alias in rule.aliases):
            return rule
    return None


def check_medication_timing(items: list) -> list:
    """
    Check a list of medications/supplements/foods against known
    levothyroxine timing interactions. Deterministic lookup, no LLM call.
    """
    results = []
    for raw_item in items:
        normalized = raw_item.strip().lower()
        rule = _find_rule(normalized)
        if rule:
            results.append(
                TimingGuidance(
                    item=raw_item,
                    matched=True,
                    min_hours_apart=rule.min_hours_apart,
                    guidance=rule.guidance,
                    severity=rule.severity,
                    source_note=rule.source_note,
                )
            )
        else:
            results.append(
                TimingGuidance(
                    item=raw_item,
                    matched=False,
                    min_hours_apart=None,
                    guidance=(
                        f"No known levothyroxine timing interaction on file for "
                        f"'{raw_item}'. As a general rule, take levothyroxine "
                        "consistently at the same time each day on an empty "
                        "stomach, and ask your pharmacist about anything new."
                    ),
                    severity=InteractionSeverity.NO_KNOWN_INTERACTION,
                    source_note="Not in the known-interaction list — absence of a match is not confirmation of safety.",
                )
            )
    return results

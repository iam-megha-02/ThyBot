"""
Structured extraction of thyroid lab values (TSH, T3, T4) from raw text
pulled out of an uploaded lab report PDF.

Deterministic regex parsing, not an LLM call — the report's own printed
value/range/unit is the source of truth; nothing here gets to guess or
round a number. Built against a real bootlab.in-style report layout
(see tests), where PDF table extraction glues cell text together
("ThyroidStimulating" with no space) and drops most whitespace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LabResult:
    test: str                       # canonical name: "TSH", "T3", "T4"
    variant: str                    # "free", "total", or "unspecified"
    value: float
    unit: Optional[str]
    reference_low: Optional[float]
    reference_high: Optional[float]
    reported_status: Optional[str]  # "Normal" / "High" / "Low" as printed on the report
    raw_snippet: str                # matched text window, kept for audit/debugging


_NUMBER = r"(\d+\.?\d*)"
_RANGE = rf"{_NUMBER}\s*(?:-|–|—|to)\s*{_NUMBER}"
_STATUS_WORDS = ("normal", "borderline", "high", "low")

# Order matters: more specific ("free t3") must be checked before the
# generic fallback ("t3") so a report that actually says "Free T3" isn't
# mis-tagged as Total T3.
_TEST_DEFINITIONS = (
    ("TSH", "unspecified", ("thyroid stimulating hormone", "thyroid-stimulating hormone", "tsh"),
        ("miu/l", "uiu/ml", "µiu/ml", "iu/l")),
    ("T3", "free", ("free t3", "ft3"), ("pg/ml", "pmol/l")),
    ("T3", "total", ("triiodothyronine", "t3"), ("ng/dl", "ng/ml")),
    ("T4", "free", ("free t4", "ft4"), ("ng/dl", "pmol/l")),
    ("T4", "total", ("thyroxine", "t4"), ("µg/dl", "ug/dl", "mcg/dl")),
)

_DATE_PATTERNS = (
    r"sample collection date[:\s]*([0-9]{4}-[0-9]{2}-[0-9]{2})",
    r"collection date[:\s]*([0-9]{4}-[0-9]{2}-[0-9]{2})",
    r"report date[:\s]*([0-9]{4}-[0-9]{2}-[0-9]{2})",
)

# Deliberately generous — this is a sanity check to catch a parser
# grabbing the wrong number entirely, not a clinical reference range.
# Free and Total ranges for the same analyte differ by orders of
# magnitude, so anything tighter would false-flag valid reports.
_PLAUSIBLE_VALUE_RANGE = {
    "TSH": (0.0, 100.0),
    "T3": (0.0, 1000.0),
    "T4": (0.0, 1000.0),
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def extract_collection_date(raw_text: str) -> Optional[str]:
    lowered = _normalize(raw_text).lower()
    for pattern in _DATE_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            return match.group(1)
    return None


def _next_alias_position(lowered_text: str, start: int, exclude_canonical: str) -> list:
    positions = []
    for canonical_name, _, aliases, _ in _TEST_DEFINITIONS:
        if canonical_name == exclude_canonical:
            continue  # "t3" is itself a substring of "ft3" — never use a same-analyte
            # alias (free or total) as the boundary for this analyte's own window.
        for alias in aliases:
            idx = lowered_text.find(alias, start)
            if idx != -1:
                positions.append(idx)
    return positions


def _parse_value_after(text: str, lowered_text: str, start: int, own_canonical: str, hard_cap: int = 200) -> Optional[dict]:
    # Cap the search window at whichever comes first: the next *other*
    # analyte's alias, or a hard character limit — prevents a short row
    # from bleeding into the next row's numbers on a tightly packed
    # table, without this analyte's own aliases (e.g. "T3" inside "FT3")
    # truncating its own window.
    boundary_candidates = [c for c in _next_alias_position(lowered_text, start, own_canonical) if c > start]
    end = min([start + hard_cap] + boundary_candidates)

    # Strip parenthetical asides first — an abbreviation like "(FT3)" or
    # "(T4)" contains a digit that would otherwise be mistaken for the
    # reported value.
    window_text = re.sub(r"\([^)]*\)", "", text[start:end])
    window_lower = re.sub(r"\([^)]*\)", "", lowered_text[start:end])

    value_match = re.search(_NUMBER, window_text)
    if not value_match:
        return None

    range_match = re.search(_RANGE, window_text)
    status = next((w.capitalize() for w in _STATUS_WORDS if w in window_lower), None)

    return {
        "value": float(value_match.group(1)),
        "ref_low": float(range_match.group(1)) if range_match else None,
        "ref_high": float(range_match.group(2)) if range_match else None,
        "status": status,
        "snippet": window_text.strip(),
    }


def extract_lab_values(raw_text: str) -> list:
    """
    Parse TSH/T3/T4 out of raw lab-report text. Returns one LabResult per
    test found — silently skips a test not present rather than guessing,
    and skips a definition already claimed by a more specific match
    (e.g. won't double-count "T3" once "Free T3" has matched).
    """
    text = _normalize(raw_text)
    lowered = text.lower()

    results = []
    claimed = []  # (canonical_name, variant) pairs already matched

    for canonical_name, variant, aliases, unit_hints in _TEST_DEFINITIONS:
        if any(name == canonical_name for name, _ in claimed):
            continue  # a more specific variant of this test already matched

        idx = next((lowered.find(a) for a in aliases if lowered.find(a) != -1), -1)
        if idx == -1:
            continue

        matched_alias = next(a for a in aliases if lowered.find(a) == idx)
        parsed = _parse_value_after(text, lowered, idx + len(matched_alias), own_canonical=canonical_name)
        if not parsed:
            continue

        unit = next((u for u in unit_hints if u in parsed["snippet"].lower()), None)

        results.append(
            LabResult(
                test=canonical_name,
                variant=variant,
                value=parsed["value"],
                unit=unit,
                reference_low=parsed["ref_low"],
                reference_high=parsed["ref_high"],
                reported_status=parsed["status"],
                raw_snippet=parsed["snippet"],
            )
        )
        claimed.append((canonical_name, variant))

    return results


def is_plausible(result: LabResult) -> bool:
    """Loose sanity check — catches a parser grabbing the wrong number, not clinical validation."""
    low, high = _PLAUSIBLE_VALUE_RANGE.get(result.test, (0.0, float("inf")))
    return low <= result.value <= high

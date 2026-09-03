"""Measure the Repair Convention's own claims about retained evidence, rather than trusting them.

The convention tells an agent which tokens a repair consumes and where the pairing digits are
visible. Both are claims about what a real run produces, so they are checked against one.
"""

import json
from pathlib import Path
from typing import Any, cast

import yaml

from tests.prepare.repair_fixtures import CONSUMED_TOKENS, declarations, hand_rolled_repair
from tests.support.public_cli import run_cli

CONVENTIONS = Path("src/galley/skills/galley/resources/repair-conventions.yaml")
PAUL_GRAHAM = "paul-graham-hand-rolled-endnotes"
SOCIAL_EMBED = "substack-markdown-social-embed"
MARKERS = ("1", "2")
ARGUMENTS = ("--profile", "x4-crosspoint", "--json")


def _convention(identifier: str) -> dict[str, object]:
    data = cast(dict[str, Any], yaml.safe_load(CONVENTIONS.read_text(encoding="utf-8")))
    return next(entry for entry in data["conventions"] if entry["id"] == identifier)


def test_the_social_embed_convention_is_source_specific_and_self_contained() -> None:
    convention = _convention(SOCIAL_EMBED)

    assert convention["source"] == "observed Substack Markdown export"
    assert "not a fact about Markdown" in cast(str, convention["why_not_general"])


def test_an_ambiguous_social_carrier_is_preserved_for_bespoke_repair() -> None:
    """Recognition is bounded by complete evidence; it is never a licence to fill gaps."""

    convention = _convention(SOCIAL_EMBED)
    carriers = cast(list[dict[str, str]], convention["carriers"])

    assert [carrier["kind"] for carrier in carriers] == ["markdown"]
    assert "identity" in cast(str, convention["complete_when"])
    assert "timestamp" in cast(str, convention["complete_when"])
    ambiguity = cast(str, convention["preserve_when_ambiguous"])
    assert "leave the carrier unchanged" in ambiguity
    assert "Bespoke Repair" in ambiguity


def test_the_social_convention_covers_both_observed_wrapper_positions() -> None:
    """The observed export closes one wrapper before its body and another after it."""

    convention = _convention(SOCIAL_EMBED)
    carrier = cast(list[dict[str, str]], convention["carriers"])[0]
    recognition = cast(str, convention["pairing_key"])

    assert "early-close variant" in recognition
    assert "immediately after identity" in recognition
    assert "body link to that same URL" in recognition
    assert "late-close variant" in recognition
    assert "optional media" in recognition
    assert "early-close layout" in carrier["definition"]
    assert "late-close layout" in carrier["definition"]


def test_the_convention_names_both_decided_carriers_and_one_pairing_key() -> None:
    """One convention naming two shapes, because the matching key is identical across them."""

    convention = _convention(PAUL_GRAHAM)
    carriers = cast(list[dict[str, str]], convention["carriers"])

    assert {carrier["kind"] for carrier in carriers} == {"article-url", "markdown"}
    assert "visible digit" in cast(str, convention["pairing_key"])
    assert carriers[0]["pairing_evidence"] == "read the digit from the anchor's visible text"
    assert carriers[1]["pairing_evidence"] == "read the digit from the link text"


def test_every_pairing_digit_is_visible_twice_in_the_retained_baseline(tmp_path: Path) -> None:
    """The convention pairs on a visible digit, so each one must be in the evidence to pair on."""

    _, repair = hand_rolled_repair(tmp_path)
    baseline = repair.baseline.read_text(encoding="utf-8")

    for marker in MARKERS:
        assert baseline.count(f"[{marker}]") == 2


def test_only_the_sections_heading_word_is_consumed_by_the_repair(tmp_path: Path) -> None:
    """Declaring more than a repair truly consumes is how real loss hides behind a declaration."""

    source, repair = hand_rolled_repair(tmp_path)
    declared = declarations(tmp_path / "expected.json", CONSUMED_TOKENS)

    result = run_cli(
        "prepare",
        str(source),
        "--output",
        str(tmp_path / "book-0.epub"),
        *ARGUMENTS,
        "--expected-missing-tokens",
        str(declared),
        *repair.options,
    )
    report: Any = json.loads(result.stdout)
    tokens = report["artifact"]["text_preservation"]["tokens"]

    assert result.returncode == 0
    # The convention's claim, measured: each digit survives twice — as its reference number
    # and as its "Footnote N." label — so no digit is expected missing, and the notes
    # section's own heading word is the entire residue.
    assert [entry["token"] for entry in tokens["expected_missing"]] == ["Notes"]
    assert tokens["unexpected_missing"] == []
    assert set(MARKERS).isdisjoint(
        entry["token"] for entry in tokens["expected_missing"] + tokens["unexpected_missing"]
    )

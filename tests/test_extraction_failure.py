"""Infer Extraction Failure from the one measured-document rule."""

import json
from pathlib import Path
from typing import Any

from tests.article_fixtures import (
    ARTICLE,
    words_article,
)
from tests.article_server import (
    MALFORMED_DEFUDDLE,
    served,
    write_command,
)
from tests.public_cli import NO_DEFUDDLE, run_public_cli

THRESHOLD = 300
BOUNDARY = "extraction-failure"
RULE = "extraction-failure/1"
# A known false negative: a link-aggregator front page that parses 699 words of listing table.
# The rule deliberately does not classify it, leaving it to the agent rather than inventing a
# second heuristic.
FALSE_NEGATIVE = "link-aggregator-front-page"


def refuse(source: str) -> list[Any]:
    results = run_public_cli("inspect", source, "--profile", "x4-crosspoint", "--json")
    assert [(result.returncode, result.stderr) for result in results] == [(3, ""), (3, "")]
    return [json.loads(result.stdout) for result in results]


def complete(source: str) -> list[Any]:
    results = run_public_cli("inspect", source, "--profile", "x4-crosspoint", "--json")
    assert [(result.returncode, result.stderr) for result in results] == [(0, ""), (0, "")]
    return [json.loads(result.stdout) for result in results]


def test_the_threshold_is_strict_at_three_hundred_words() -> None:
    """299 refuses and 300 completes; the boundary is a decision, not an approximation."""

    with served(words_article(THRESHOLD - 1)) as url:
        for report in refuse(url):
            assert report["refusal"]["boundary"] == BOUNDARY
            assert report["extraction"]["words"]["value"] == THRESHOLD - 1

    with served(words_article(THRESHOLD)) as url:
        for report in complete(url):
            assert report["extraction"]["words"]["value"] == THRESHOLD


def test_the_refusal_states_the_rule_the_measurement_and_the_documents_behind_it() -> None:
    """The threshold's evidence is readable in the Report."""

    with served(words_article(12)) as url:
        for report in refuse(url):
            refusal = report["refusal"]
            assert refusal["boundary"] == BOUNDARY
            assert refusal["stage"] == "extraction-assessment"
            assert refusal["artifact_written"] is False
            assert refusal["fact"]["inferred"] is True
            basis = refusal["basis_for_inference"]
            assert basis["rule"] == RULE
            assert basis["threshold"]["value"] == THRESHOLD
            assert basis["measured"]["value"] == 12
            assert basis["relation"] == "fewer-than"
            assert basis["extractor_status"] == "ok"
            # The count of real documents standing behind the rule, and its contrast case.
            assert basis["verified_failure_documents"]["value"] == 9
            assert basis["evidence_documents"]["value"] == 10
            assert basis["known_false_negative"]["case"] == FALSE_NEGATIVE
            assert basis["known_false_negative"]["words"]["value"] == 699


def test_a_zero_word_extraction_is_judged_by_the_same_rule() -> None:
    """Defuddle's documented no-content exit is a fact about the page, evaluated as zero words."""

    with served(
        "<!doctype html><html><head><title>Empty</title></head><body></body></html>"
    ) as url:
        for report in refuse(url):
            refusal = report["refusal"]
            assert refusal["boundary"] == BOUNDARY
            assert refusal["basis_for_inference"]["measured"]["value"] == 0
            assert report["extraction"]["no_content"] is True
            assert report["extraction"]["words"]["value"] == 0


def test_a_tool_failure_is_never_an_extraction_failure(tmp_path: Path) -> None:
    """A dependency that did not run says nothing about whether the page holds a work."""

    malformed = write_command(tmp_path / "defuddle", MALFORMED_DEFUDDLE)
    with served(ARTICLE) as url:
        for environment in (NO_DEFUDDLE, {"GALLEY_DEFUDDLE": str(malformed)}):
            results = run_public_cli(
                "inspect", url, "--profile", "x4-crosspoint", "--json", environment=environment
            )

            assert [result.returncode for result in results] == [3, 3]
            for result in results:
                refusal = json.loads(result.stdout)["refusal"]
                # Absent dependency and failed extraction are different boundaries; neither is
                # the inference, and neither carries a basis.
                assert refusal["boundary"] in {
                    "dependency-unavailable",
                    "extraction-tool-failure",
                }
                assert refusal["boundary"] != "extraction-failure"
                assert refusal["basis_for_inference"] is None


def test_the_known_false_negative_completes_rather_than_being_forced() -> None:
    """The CLI does not add a second heuristic merely to catch one known false negative."""

    with served(words_article(699)) as url:
        for report in complete(url):
            assert report["extraction"]["words"]["value"] == 699
            assert report["outcome"] == "completed"
            assert report["refusal"] is None
            # The primitives an agent judges `boundary-chrome-presence` from stay reported, and
            # the CLI states no verdict of its own about them.
            assert report["canonical_document"]["reading"]["links"]["basis"] == "measured"
            assert report["extraction"]["words"]["basis"] == "measured"

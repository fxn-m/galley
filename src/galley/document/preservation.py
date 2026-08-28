"""Compare a Preservation Baseline with reader-visible artifact text."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import cast
from unicodedata import normalize

from galley.document.discards import Discard, discard_facts
from galley.report.quantities import quantity

APOSTROPHES = frozenset({"'", "’"})
# Why a run makes no Text Preservation claim. The first is `audit` with no retained source
# evidence to compare against; the second is a baseline that was taken after the reader had
# already dropped something, so what it proves is narrower than what the claim would say.
BASELINE_UNAVAILABLE = "preservation-baseline-unavailable"
DISCARDED_REASON = "source-reader-discarded-content"
# Each reason in the words a person reads, carried in the Report beside the name rather than
# looked up by whoever renders it. A Report that has to be joined to a table to be understood is
# one an agent reads differently from a terminal.
DETAILS = {
    BASELINE_UNAVAILABLE: "Preservation Baseline unavailable",
    DISCARDED_REASON: "the source reader discarded content before the baseline was taken",
}
TOKEN_DEFINITION = (
    "case-sensitive Unicode alphanumeric sequences retaining an internal straight or curly "
    "apostrophe"
)


@dataclass(frozen=True)
class TextPreservation:
    """Measured preservation facts and the unexpected token losses that may refuse prepare."""

    facts: dict[str, object]
    unexpected_missing: dict[str, int]

    @property
    def unexpected_facts(self) -> list[dict[str, object]]:
        """Expose structured missing-token facts without leaking the Report's nested shape."""

        tokens = cast(dict[str, object], self.facts["tokens"])
        return cast(list[dict[str, object]], tokens["unexpected_missing"])


@dataclass(frozen=True)
class ExpectedMissing:
    """Validated expected-loss declarations, or why their file could not be used."""

    tokens: dict[str, int] | None
    reason: str | None = None
    detail: str = ""


def read_expected_missing(path: Path | None) -> ExpectedMissing:
    """Read the UTF-8 JSON token-to-count object accepted by the public prepare interface."""

    if path is None:
        return ExpectedMissing({})
    try:
        parsed = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return ExpectedMissing(None, "missing", "the declarations file does not exist")
    except UnicodeDecodeError:
        return ExpectedMissing(None, "not-utf8", "the declarations file is not UTF-8")
    except json.JSONDecodeError as error:
        return ExpectedMissing(None, "malformed-json", str(error))
    except OSError as error:
        return ExpectedMissing(None, "unreadable", str(error))
    if not isinstance(parsed, dict):
        return ExpectedMissing(None, "invalid-shape", "expected a JSON object")
    tokens: dict[str, int] = {}
    for token, count in cast(dict[str, object], parsed).items():
        if normalize("NFC", token) != token or _tokens(token) != [token]:
            return ExpectedMissing(None, "invalid-token", f"not one exact NFC word token: {token}")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            return ExpectedMissing(None, "invalid-count", f"expected a non-negative count: {token}")
        tokens[token] = count
    return ExpectedMissing(tokens)


def compare_text(
    baseline: str,
    artifact_segments: Sequence[str],
    expected_missing: Mapping[str, int] | None = None,
    *,
    discarded: Sequence[Discard] = (),
) -> TextPreservation:
    """Subtract artifact tokens from baseline tokens without treating additions as loss.

    What was declared is recorded beside what actually went missing. An allowed loss is evidence
    a repair states about itself, so it belongs in the Report whether or not it fired: a
    declaration visible only when it matches turns an intentional loss into a silent exception,
    and a declaration that never fires is worth seeing too.

    **The claim stops where the baseline starts.** A baseline rendered from the AST cannot see
    text the reader dropped before that AST existed, so a run whose reader reported a discard
    measures everything here and claims nothing: the measurement is still true of what Galley was
    handed, and saying so with `claimed` still set would be that truth standing in for a wider one.
    """

    baseline_text = normalize("NFC", baseline)
    artifact_text = normalize("NFC", "\n".join(artifact_segments))
    baseline_tokens = Counter(_tokens(baseline_text))
    artifact_tokens = Counter(_tokens(artifact_text))
    missing = baseline_tokens - artifact_tokens
    allowed = Counter(expected_missing or {})
    expected = missing & allowed
    unexpected = missing - allowed
    facts: dict[str, object] = {
        "basis": "measured",
        "claimed": not discarded,
        "detail": DETAILS[DISCARDED_REASON] if discarded else None,
        "discarded": discard_facts(discarded),
        "reason": DISCARDED_REASON if discarded else None,
        "normalization": "NFC",
        "tokens": {
            "added": quantity(sum((artifact_tokens - baseline_tokens).values()), "tokens"),
            "artifact": quantity(artifact_tokens.total(), "tokens"),
            "baseline": quantity(baseline_tokens.total(), "tokens"),
            "declared": _multiset(allowed),
            "definition": TOKEN_DEFINITION,
            "expected_missing": _multiset(expected),
            "unexpected_missing": _multiset(unexpected),
        },
        "characters": {
            "added": quantity(
                sum((Counter(artifact_text) - Counter(baseline_text)).values()), "characters"
            ),
            "artifact": quantity(len(artifact_text), "characters"),
            "authoritative": False,
            "baseline": quantity(len(baseline_text), "characters"),
            "identical": baseline_text == artifact_text,
            "missing": quantity(
                sum((Counter(baseline_text) - Counter(artifact_text)).values()), "characters"
            ),
        },
    }
    return TextPreservation(facts, dict(sorted(unexpected.items())))


def count_words(baseline: str) -> int:
    """Count the reader-visible word tokens one Preservation Baseline carries.

    This is the same tokenisation Text Preservation subtracts with, deliberately: a word count
    Galley states and a word count Galley enforces must never be able to disagree about what a
    word is.
    """

    return len(_tokens(normalize("NFC", baseline)))


def unavailable_text_preservation() -> dict[str, object]:
    """State why an audit without source evidence makes no Text Preservation claim."""

    return {
        "claimed": False,
        "detail": DETAILS[BASELINE_UNAVAILABLE],
        "reason": BASELINE_UNAVAILABLE,
    }


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for index, character in enumerate(text):
        if character.isalnum():
            current.append(character)
        elif (
            character in APOSTROPHES
            and current
            and index + 1 < len(text)
            and text[index + 1].isalnum()
        ):
            current.append(character)
        else:
            _finish(tokens, current)
    _finish(tokens, current)
    return tokens


def _finish(tokens: list[str], current: list[str]) -> None:
    if current:
        tokens.append("".join(current))
        current.clear()


def _multiset(tokens: Mapping[str, int]) -> list[dict[str, object]]:
    return [
        {"count": quantity(count, "tokens"), "token": token}
        for token, count in sorted(tokens.items())
        if count > 0
    ]

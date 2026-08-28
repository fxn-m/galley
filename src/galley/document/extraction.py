"""Infer Extraction Failure from the one rule measured documents support, and no other.

Extraction Failure is not observable from the extractor's own status: a 751-page survey found
that all nine verified failures returned `status: ok` with a stub. Galley therefore uses one
reader-visible word measurement against one threshold and carries the evidence counts into the
Report.

There is deliberately no second quality rule. A link-aggregator front page parsed 699 words and
is a known false negative, but its link-to-prose shape remains an agent judgement. Adding another
threshold merely to catch it would turn an unsupported heuristic into product behaviour.
"""

from dataclasses import dataclass

from galley.report.quantities import quantity, reported

RULE = "extraction-failure/1"
WORD_COUNT_THRESHOLD = 300
RELATION = "fewer-than"
# Nine documents were verified as failures. The evidence set adds one contrast document that must
# keep completing, which makes the boundary a measurement rather than a floor chosen to fit.
VERIFIED_FAILURE_DOCUMENTS = 9
EVIDENCE_DOCUMENTS = 10
CONTRAST_CASE = "long-form-article"
FALSE_NEGATIVE_CASE = "link-aggregator-front-page"
FALSE_NEGATIVE_WORDS = 699

SUMMARY = (
    "the extracted work is too short to be an Article-Like Page Galley can prepare: "
    "{measured} reader-visible words, fewer than the {threshold} this rule requires"
)


@dataclass(frozen=True)
class ExtractionFailure:
    """One evaluation of the Extraction Failure rule against one parsed document."""

    measured: int
    extractor_status: str

    @property
    def inferred(self) -> bool:
        """Say whether this document falls below the decided threshold.

        Strict on purpose: 300 completes and 299 refuses. A boundary that moved with rounding
        would not be the measured boundary.
        """

        return self.measured < WORD_COUNT_THRESHOLD

    @property
    def fact(self) -> dict[str, object]:
        """State that this refusal is an inference rather than an observed extractor result."""

        return {
            "inferred": True,
            "measured_words": quantity(self.measured, "words"),
            "rule": RULE,
        }

    @property
    def basis(self) -> dict[str, object]:
        """Carry the threshold and the documents standing behind it into the Report.

        The count of measured documents travels beside the threshold so its evidence is checkable
        when the Report is read, rather than only when this module is reviewed.
        """

        return {
            "contrast_case": CONTRAST_CASE,
            "evidence_documents": reported(EVIDENCE_DOCUMENTS, "documents"),
            "extractor_status": self.extractor_status,
            "known_false_negative": {
                "case": FALSE_NEGATIVE_CASE,
                "detail": (
                    "a link-aggregator front page this rule deliberately does not classify; "
                    "its link-to-prose shape is left for agent judgement"
                ),
                "words": reported(FALSE_NEGATIVE_WORDS, "words"),
            },
            "measured": quantity(self.measured, "words"),
            "relation": RELATION,
            "rule": RULE,
            "threshold": reported(WORD_COUNT_THRESHOLD, "words"),
            "verified_failure_documents": reported(VERIFIED_FAILURE_DOCUMENTS, "documents"),
        }

    @property
    def summary(self) -> str:
        """Say what was measured and what was required, in the reader's own terms."""

        return SUMMARY.format(measured=self.measured, threshold=WORD_COUNT_THRESHOLD)


def assess_extraction(measured: int, extractor_status: str) -> ExtractionFailure:
    """Evaluate one parsed document's reader-visible word count against the decided rule."""

    return ExtractionFailure(measured, extractor_status)

"""Locate a stated author inside the text it was taken from, without judging whether it is a name.

An extractor reads a byline off a page and can be wrong about it. One measured page reported
"constantly rewriting the todo list, Manus is", a clause lifted from the article body, and the
book carried it as its author on the title page.

Galley does not repair that, because it cannot. Every rule that would discard the Manus clause
also discards a real author: the occurrence test alone takes out Gwern, Eliezer S. Yudkowsky and
the Department for Business and Trade, all correct, all of whom write their own names into their
own prose. Every measured occurrence sits mid-sentence, so no boundary test separates them
either. What remains -- word count, capitalisation, whether the string ends on a verb -- is only
guessing at what a name looks like.

So this module measures and quotes. It says where the stated author occurs in the reader-visible
text and hands back the sentence around it, and the agent that reads the Report decides whether it
is a byline or a fragment -- a judgment it can make from one line of context and Galley cannot make
at all.
"""

from galley.report.quantities import quantity

CONTEXT_LIMIT = 160
"""Characters of surrounding text to quote, enough for a sentence and short enough to read."""

SENTENCE_ENDS = ".!?"
"""A sentence ends on one of these only when whitespace follows it.

Without that condition the quote for `Gwern` stops at "Gwern." and hides the ".net" that makes it
a domain rather than a byline -- cutting away exactly the context the reader of the fact needs.
"""


def author_occurrence(author: str | None, baseline: str) -> dict[str, object] | None:
    """Say whether a stated author occurs in the document's own text, and quote where it does.

    Absent rather than false where there is no author to look for, because a document that
    states none has nothing to report and an absent fact says that where a false one would not.
    """

    if not author or not baseline:
        return None
    index = baseline.find(author)
    if index < 0:
        return {"occurrences": quantity(0, "occurrences"), "stated": author}
    return {
        "context": _sentence(baseline, index, len(author)),
        "occurrences": quantity(baseline.count(author), "occurrences"),
        "stated": author,
    }


def _sentence(baseline: str, index: int, length: int) -> str:
    """Quote the sentence the author was found in, bounded so a long paragraph stays readable."""

    start = max(0, index - CONTEXT_LIMIT)
    end = min(len(baseline), index + length + CONTEXT_LIMIT)
    window = baseline[start:end]
    offset = index - start
    return " ".join(window[_opened(window, offset) : _closed(window, offset + length)].split())


def _opened(window: str, offset: int) -> int:
    """Find where the sentence containing the match begins within the quoted window."""

    for position in range(offset - 1, -1, -1):
        if _ends(window, position):
            return position + 1
    return 0


def _closed(window: str, offset: int) -> int:
    """Find where the sentence containing the match ends within the quoted window."""

    for position in range(offset, len(window)):
        if _ends(window, position):
            return position + 1
    return len(window)


def _ends(window: str, position: int) -> bool:
    """Say whether a sentence ends at this character, which a full stop alone does not settle."""

    if window[position] == "\n":
        return True
    if window[position] not in SENTENCE_ENDS:
        return False
    following = window[position + 1 : position + 2]
    return following == "" or following.isspace()

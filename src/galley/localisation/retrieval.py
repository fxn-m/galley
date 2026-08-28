"""Retrieve one reference's bytes and say what they turned out to be, or why they never arrived.

The retrieval and the measurement are one step because neither settles the question alone: bytes
that arrived but do not measure as an image are as useless to a book as bytes that never came, and
a name for them can only be chosen once they have been measured. Galley never reads a media type
off a filename or a response header, so this runs the other way round — the bytes decide, and the
file is named after what they are.
"""

from galley.images.measurement import measure_image
from galley.localisation.records import RETRIEVED, Retrieval
from galley.localisation.references import Reference
from galley.localisation.refusals import LocalisationRefusal
from galley.tools.fetching import Addresses, fetch_reference

UNDECODABLE = "undecodable"
RETRIEVAL_STAGE = "image-retrieval"
# A failure the address rule caught rather than the transport, which is a different thing to tell
# a reader: nothing was sent, and the reference named somewhere Galley will not ask.
BLOCKED = frozenset({"blocked-host", "unresolvable-host"})
# The extension one retrieved image's evidence file takes, from what its bytes measured as. This
# is not `images/resources.py`'s map, which names the two encodings preservation keeps unchanged;
# a type with no entry here is one Galley would not package at all, so the reference refuses
# rather than being written under a name nobody chose.
EVIDENCE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}


def retrieval(reference: Reference, permitted: Addresses) -> Retrieval:
    """Fetch one reference and measure whatever came back, never trusting what it was labelled."""

    answer = fetch_reference(reference.locator, permitted=permitted)
    if answer.data is None:
        return Retrieval(
            reference,
            outcome=answer.reason or "http-error",
            detail=answer.detail,
            addresses=answer.addresses,
            status=answer.status,
        )
    measurement = measure_image(answer.data)
    extension = EVIDENCE_EXTENSIONS.get(measurement.media_type or "")
    if extension is None:
        return Retrieval(
            reference,
            outcome=UNDECODABLE,
            detail=f"{reference.locator} did not measure as an image Galley packages",
            addresses=answer.addresses,
            status=answer.status,
            data=answer.data,
        )
    return Retrieval(
        reference,
        outcome=RETRIEVED,
        addresses=answer.addresses,
        status=answer.status,
        data=answer.data,
        media_type=measurement.media_type,
        name=f"{reference.identifier}{extension}",
    )


def unretrieved(attempt: Retrieval) -> LocalisationRefusal:
    """Name the reference that stopped the run, and the boundary its failure belongs to."""

    boundary = "blocked-image-host" if attempt.outcome in BLOCKED else "unretrievable-image"
    return LocalisationRefusal(
        boundary=boundary,
        stage=RETRIEVAL_STAGE,
        summary=f"cannot retrieve a referenced image: {attempt.detail}",
        fact={
            "addresses": list(attempt.addresses),
            "detail": attempt.detail,
            "identifier": attempt.reference.identifier,
            "locator": attempt.reference.locator,
            "reason": attempt.outcome,
            "status": attempt.status,
        },
    )

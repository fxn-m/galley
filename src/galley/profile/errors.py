"""The profile-error document `profiles show --json` emits, validated like every output.

Profile commands produce no Report, whose shape does not fit them; this is their one structured
failure document. Constructing it through a schema keeps the CLI free of hand-built
JSON, so no output path exists that validation never sees.
"""

from galley.validation import load_schema

PROFILE_ERROR_SCHEMA, PROFILE_ERROR_VALIDATOR = load_schema("profile-error.json")


def profile_error_document(profile_id: str, message: str) -> dict[str, object]:
    """State one unknown-profile failure as the versioned profile-error document."""

    document: dict[str, object] = {
        "error": {"code": "unknown-profile", "message": message, "profile": profile_id},
        "outcome": "invocation-error",
        "schema": "galley/profile-error/1",
    }
    PROFILE_ERROR_VALIDATOR.validate(document)
    return document

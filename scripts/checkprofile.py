"""Validate committed Device Profile data."""

from galley.profile.loading import list_profiles
from galley.profile.validation import ProfileError


def main() -> int:
    """Validate every committed profile through the public discovery interface."""

    try:
        profiles = list_profiles()
    except (OSError, ProfileError) as error:
        print(f"checkprofile: {error}")
        return 1
    print(f"checkprofile: OK ({len(profiles)} profiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

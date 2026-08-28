from galley.transforms.links import strip_links
from galley.epub.links import CountingRule
from galley.profile.loading import load_profile
from galley.document.canonical import DocumentLanguage
from galley.transforms.metadata import metadata_transforms
from galley.transforms.links import link_transform
from galley.transforms.metadata import navigation_transform

PROFILE = load_profile("x4-crosspoint")
RULE = CountingRule(excluded_schemes=frozenset({"https"}), requires_visible_text=True)
LINKED: dict[str, object] = {
    "blocks": [
        {
            "t": "Para",
            "c": [
                {
                    "t": "Link",
                    "c": [["", [], []], [{"t": "Str", "c": "away"}], ["https://e.com", ""]],
                }
            ],
        }
    ],
    "meta": {},
}


def test_navigation_depth_reports_the_activation_the_profile_decided() -> None:
    """`device_judged` is true because the same work was read at both settings.

    The depth passed here is the caller's argument rather than the profile's value, so this holds
    the record's shape and not the number the profile currently carries.
    """

    transform = navigation_transform(PROFILE, 1)

    assert transform["fired"] is True
    assert transform["activation"] == "toc_depth"
    assert transform["justified_by"] == "nav-membership-drives-pagination"
    assert transform["device_judged"] is True
    assert transform["depth"] == {"basis": "reported", "unit": "levels", "value": 1}


def test_a_profile_stating_no_navigation_depth_gets_no_invented_one() -> None:
    """Device facts live in profile data, so an absent one stays absent."""

    transform = navigation_transform({"activation": {}}, None)

    assert transform["fired"] is False
    assert transform["depth"] is None
    assert transform["device_judged"] is False
    assert transform["justified_by"] is None
    assert "activates no navigation depth" in str(transform["note"])


def test_a_profile_that_strips_no_href_still_counts_what_it_left_alone() -> None:
    """The single bundled profile activates stripping, so only a stated profile reaches this."""

    stripping = strip_links(LINKED, rule=RULE, identifiers=[], notes=0, activated=False)
    transform = link_transform({"activation": {}}, stripping)

    assert transform["fired"] is False
    assert transform["justified_by"] is None
    assert transform["device_judged"] is False
    assert stripping.ast == LINKED
    assert transform["total"] == {
        "after": {"basis": "measured", "unit": "links", "value": 1},
        "before": {"basis": "measured", "unit": "links", "value": 1},
        "removed": {"basis": "measured", "unit": "links", "value": 0},
    }
    assert "does not activate href stripping" in str(transform["note"])


def test_a_stated_author_and_an_absent_one_are_both_recorded() -> None:
    stated = metadata_transforms(
        {"title": "A Plain Book", "author": "Ada Lovelace"},
        {"title_source": "metadata"},
        DocumentLanguage("en", "metadata"),
    )
    absent = metadata_transforms(
        {"title": "plain", "author": None},
        {"title_source": "filename"},
        DocumentLanguage("und", "default"),
    )

    names = ["document-title", "document-author", "document-language"]
    assert [entry["name"] for entry in stated] == names
    assert [entry["fired"] for entry in stated] == [True, True, True]
    # The language always fires; only the author can decide not to.
    assert [entry["fired"] for entry in absent] == [True, False, True]
    assert absent[0]["title_source"] == "filename"
    assert absent[1]["author"] is None
    assert (absent[2]["language"], absent[2]["language_source"]) == ("und", "default")

import pytest

from galley.observations import (
    OBSERVATION_NAMES,
    OBSERVATION_REGISTRY,
    enabled_observations,
    observation,
)


def test_registry_contains_the_stable_observation_names() -> None:
    assert OBSERVATION_NAMES == (
        "ordered-list-numbering-loss",
        "page-break-content-destruction",
        "unrenderable-images",
        "alt-text-fallback-absence",
        "colour-meaning-collapse",
        "strikethrough-inversion",
        "table-relationship-loss",
        "code-block-reflow",
        "nested-list-flattening",
        "caption-indistinction",
        "alignment-meaning-flattening",
        "boundary-chrome-presence",
        "unrenderable-glyphs",
        "diagram-text-legibility",
        "footnote-target-reliability",
        "link-footnote-dilution",
        "pagination-granularity",
        "ingress-conversion-acceptance",
        "library-title-presentation",
        "library-author-presentation",
        "library-cover-presentation",
        "navigation-usability",
        "typography-preservation",
        "colour-image-presentation",
        "footnote-usability",
        "theme-adaptation",
        "large-text-adaptation",
    )
    assert len(OBSERVATION_NAMES) == len(set(OBSERVATION_NAMES))


def test_every_observation_declares_its_layer_and_consequence() -> None:
    evidence_levels = {"computable", "flaggable", "device-judged"}
    consequences = {
        "content-loss",
        "semantic-inversion",
        "structure-loss",
        "legibility",
        "navigation",
        "contamination",
    }

    assert set(OBSERVATION_REGISTRY) == set(OBSERVATION_NAMES)
    for name, (evidence, consequence) in OBSERVATION_REGISTRY.items():
        assert evidence in evidence_levels, name
        assert consequence in consequences, name


def test_a_computable_observation_may_carry_a_boolean_judgement() -> None:
    entry = observation("footnote-target-reliability", applicability=True, fired=True)

    assert entry["evidence"] == "computable"
    assert entry["consequence"] == "navigation"
    assert entry["fired"] is True


@pytest.mark.parametrize(
    "name", ("link-footnote-dilution", "diagram-text-legibility", "pagination-granularity")
)
def test_the_cli_may_never_decide_a_flaggable_or_device_judged_observation(name: str) -> None:
    outstanding = observation(name, applicability=True, fired=None)
    assert outstanding["fired"] is None

    with pytest.raises(ValueError, match="the CLI may not decide"):
        _ = observation(name, applicability=True, fired=False)


def test_activation_comes_from_profile_data_in_registry_order() -> None:
    profile: dict[str, object] = {
        "observations": [
            {"name": "link-footnote-dilution", "enabled": True},
            {"name": "unrenderable-glyphs", "enabled": False},
            {"name": "ordered-list-numbering-loss"},
        ]
    }

    assert enabled_observations(profile) == [
        "ordered-list-numbering-loss",
        "link-footnote-dilution",
    ]

"""Keep new Delivery evidence versioned without invalidating historical records."""

from copy import deepcopy
from pathlib import Path

from galley.documents import validate_document
from tests.crosspoint_server import crosspoint
from tests.delivery_fixtures import plan, published
from tests.workspace_fixtures import command_document, field


def test_historical_v1_record_still_selects_and_validates_its_schema(tmp_path: Path) -> None:
    """A v2 plan can be reduced to the old contract and still validate as historical v1."""

    _workspace, artifact, environment = published(tmp_path)
    with crosspoint() as (host, _device):
        current = command_document(plan(artifact, environment, host))
    historical = deepcopy(current)
    del historical["exchanges"]
    field(historical, "galley")["document_schema"] = "galley/delivery-record/1"

    validate_document(historical)

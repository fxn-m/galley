"""Ask one trusted target what it is, and write both answers into the document that asked.

`device status` and `deliver` perform the same probe, and both have to keep what it found even
when it ends in refusal: a device that answered but is not an X4 has still told Galley its
firmware and mode, and dropping that with the refusal would leave a user guessing what they had
plugged in. So the target's resolved addresses are recorded before the request is made, and the
device's whole status response before the model is judged.
"""

from dataclasses import dataclass

from galley.delivery.crosspoint import CrossPointClient, DeviceStatus
from galley.delivery.refusals import DeliveryRefusal
from galley.delivery.targets import DeliveryTarget, trusted_target
from galley.documents import CommandDocument, with_facts, with_refusal

REQUIRED_MODEL = "X4"
MODEL_STAGE = "device-model"


@dataclass(frozen=True)
class Probed:
    """One probe's document, and the client and status when it reached an X4."""

    document: CommandDocument
    client: CrossPointClient | None = None
    status: DeviceStatus | None = None

    @property
    def reached(self) -> bool:
        """Say whether an X4 answered, which is the only case a caller may continue from."""

        return self.status is not None


def probe(document: CommandDocument, host: str, timeout_seconds: float) -> Probed:
    """Validate the target, read its status, and require the model Galley prepares for."""

    target = trusted_target(host, timeout_seconds)
    if isinstance(target, DeliveryRefusal):
        return Probed(with_refusal(document, target))
    document = with_facts(document, {"device": target.facts()})
    client = CrossPointClient(target)
    status = client.status().value
    if isinstance(status, DeliveryRefusal):
        return Probed(with_refusal(document, status), client)
    document = with_facts(document, {"device": {**target.facts(), **status.facts()}})
    if status.model.strip().upper() != REQUIRED_MODEL:
        return Probed(with_refusal(document, _wrong_model(target, status)), client)
    return Probed(document, client, status)


def _wrong_model(target: DeliveryTarget, status: DeviceStatus) -> DeliveryRefusal:
    """Refuse a device that is not the one this release knows how to deliver to.

    The refusal is a Delivery fact and nothing more: the Ready Artifact and every preparation
    claim about it are untouched by what happened to be at the other end of the cable.
    """

    return DeliveryRefusal(
        boundary="unexpected-device-model",
        stage=MODEL_STAGE,
        summary=f"{target.host} reports model {status.model}, not an {REQUIRED_MODEL}",
        fact={"host": target.host, "model": status.model, "required": REQUIRED_MODEL},
    )

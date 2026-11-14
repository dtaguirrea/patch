from collections.abc import Collection, Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    FiniteFloat,
    JsonValue,
    PlainSerializer,
    StrictBool,
    StringConstraints,
    model_validator,
)

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
METSeconds = Annotated[int, Field(strict=True, ge=0)]
Version = Annotated[int, Field(strict=True, ge=0)]
TelemetryValue = Annotated[FiniteFloat, Field(strict=True)]
Evidence = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_json(item) for item in value]
    return value


# Freeze nested event and message data while keeping the wire format ordinary JSON.
JSONSnapshot = Annotated[
    Mapping[str, JsonValue],
    BeforeValidator(_plain_json),
    AfterValidator(_freeze_json),
    PlainSerializer(_plain_json, return_type=dict[str, JsonValue]),
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class LinkStatus(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class TelemetryQuality(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    SUSPECT = "suspect"


class ClinicalState(StrEnum):
    MONITORING = "MONITORING"
    INITIAL_CHECK = "INITIAL_CHECK"
    CRITICAL = "CRITICAL"
    URGENT_RECHECK = "URGENT_RECHECK"
    STABLE_ASSESSMENT = "STABLE_ASSESSMENT"
    CLOSED = "CLOSED"


class FindingStatus(StrEnum):
    PRESENT = "present"
    DENIED = "denied"
    UNKNOWN = "unknown"
    NOT_ASSESSED = "not_assessed"


class FindingCategory(StrEnum):
    SYMPTOM = "symptom"
    HISTORY = "history"
    VITAL_SIGN = "vital_sign"
    PHYSICAL_EXAM = "physical_exam"
    OTHER = "other"


class FindingSource(StrEnum):
    PATIENT_REPORTED = "patient_reported"
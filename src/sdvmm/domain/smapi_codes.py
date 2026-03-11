from __future__ import annotations

from typing import Literal

SmapiUpdateState = Literal[
    "not_detected",
    "detected_version_known",
    "update_available",
    "up_to_date",
    "unable_to_determine",
]

SMAPI_NOT_DETECTED_FOR_UPDATE: SmapiUpdateState = "not_detected"
SMAPI_DETECTED_VERSION_KNOWN: SmapiUpdateState = "detected_version_known"
SMAPI_UPDATE_AVAILABLE: SmapiUpdateState = "update_available"
SMAPI_UP_TO_DATE: SmapiUpdateState = "up_to_date"
SMAPI_UNABLE_TO_DETERMINE: SmapiUpdateState = "unable_to_determine"

from __future__ import annotations

from typing import Literal

SmapiLogStatusState = Literal[
    "not_found",
    "parsed",
    "unable_to_determine",
]

SMAPI_LOG_NOT_FOUND: SmapiLogStatusState = "not_found"
SMAPI_LOG_PARSED: SmapiLogStatusState = "parsed"
SMAPI_LOG_UNABLE_TO_DETERMINE: SmapiLogStatusState = "unable_to_determine"

SmapiLogSourceKind = Literal[
    "auto_detected",
    "manual",
    "none",
]

SMAPI_LOG_SOURCE_AUTO_DETECTED: SmapiLogSourceKind = "auto_detected"
SMAPI_LOG_SOURCE_MANUAL: SmapiLogSourceKind = "manual"
SMAPI_LOG_SOURCE_NONE: SmapiLogSourceKind = "none"

SmapiLogFindingKind = Literal[
    "error",
    "warning",
    "failed_mod",
    "missing_dependency",
    "runtime_issue",
]

SMAPI_LOG_ERROR: SmapiLogFindingKind = "error"
SMAPI_LOG_WARNING: SmapiLogFindingKind = "warning"
SMAPI_LOG_FAILED_MOD: SmapiLogFindingKind = "failed_mod"
SMAPI_LOG_MISSING_DEPENDENCY: SmapiLogFindingKind = "missing_dependency"
SMAPI_LOG_RUNTIME_ISSUE: SmapiLogFindingKind = "runtime_issue"

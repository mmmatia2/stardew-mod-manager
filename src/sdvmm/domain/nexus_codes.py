from __future__ import annotations

from typing import Literal

NexusIntegrationState = Literal[
    "not_configured",
    "configured",
    "invalid_auth_failure",
    "working_validated",
]

NEXUS_NOT_CONFIGURED: NexusIntegrationState = "not_configured"
NEXUS_CONFIGURED: NexusIntegrationState = "configured"
NEXUS_INVALID_AUTH_FAILURE: NexusIntegrationState = "invalid_auth_failure"
NEXUS_WORKING_VALIDATED: NexusIntegrationState = "working_validated"

NexusCredentialSource = Literal[
    "entered",
    "saved_config",
    "environment",
    "none",
]

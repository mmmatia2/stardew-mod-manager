from __future__ import annotations

from typing import Literal

RemoteRequirementState = Literal[
    "requirements_present",
    "requirements_absent",
    "requirements_unavailable",
    "no_remote_link",
]

REQUIREMENTS_PRESENT: RemoteRequirementState = "requirements_present"
REQUIREMENTS_ABSENT: RemoteRequirementState = "requirements_absent"
REQUIREMENTS_UNAVAILABLE: RemoteRequirementState = "requirements_unavailable"
NO_REMOTE_LINK_FOR_REQUIREMENTS: RemoteRequirementState = "no_remote_link"

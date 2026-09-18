"""Offline paper account/deployment binding preflight.

This module validates only configured identity consistency.  An owner
attestation reference identifies durable external evidence; it is not evidence
that this process has verified account ownership or authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import UUID


_DEPLOYMENT_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}", re.ASCII)
_ATTESTATION_REFERENCE = re.compile(
    r"owner-attestation:[A-Za-z0-9][A-Za-z0-9._/-]{2,127}", re.ASCII,
)


class PaperDeploymentBindingError(ValueError):
    """Configured paper account/deployment binding is absent or inconsistent."""

    def __init__(self) -> None:
        super().__init__("paper deployment binding rejected")


def _canonical_uuid(value: object) -> str:
    if type(value) is not str or len(value) != 36 or str(UUID(value)) != value:
        raise PaperDeploymentBindingError() from None
    return value


@dataclass(frozen=True, repr=False)
class PaperDeploymentBinding:
    """Configured identities plus a reference to external owner attestation.

    ``owner_attestation_reference`` must point to a durable, operator-supplied
    account/deployment authorization record outside this process.  Its presence
    is a preflight requirement only: this module neither retrieves nor verifies
    that record, and therefore never treats it as ownership proof.
    """

    account_id: str
    deployment_id: str
    owner_attestation_reference: str

    def __post_init__(self) -> None:
        try:
            _canonical_uuid(self.account_id)
            if (type(self.deployment_id) is not str
                    or not _DEPLOYMENT_ID.fullmatch(self.deployment_id)
                    or type(self.owner_attestation_reference) is not str
                    or not _ATTESTATION_REFERENCE.fullmatch(self.owner_attestation_reference)):
                raise PaperDeploymentBindingError()
        except PaperDeploymentBindingError:
            raise
        except Exception:
            raise PaperDeploymentBindingError() from None

    def require_match(self, *, account_id: object, deployment_id: object) -> None:
        """Reject a local component whose configured identity differs.

        Error text intentionally contains neither account nor deployment values.
        """
        try:
            if (_canonical_uuid(account_id) != self.account_id
                    or type(deployment_id) is not str
                    or deployment_id != self.deployment_id):
                raise PaperDeploymentBindingError()
        except PaperDeploymentBindingError:
            raise
        except Exception:
            raise PaperDeploymentBindingError() from None

    def require_same(self, other: object) -> None:
        """Reject a component configured with a different attestation reference."""
        if not isinstance(other, PaperDeploymentBinding) or other != self:
            raise PaperDeploymentBindingError() from None

import pytest

from execution.paper_binding import PaperDeploymentBinding, PaperDeploymentBindingError


ACCOUNT = "54c41ab9-eab7-4823-a47d-2a0b63b18590"
REFERENCE = "owner-attestation:paper-binding-fixture-20260903"
UNTRUSTED = "private-account-value-must-not-appear"


def binding(**changes) -> PaperDeploymentBinding:
    values = {
        "account_id": ACCOUNT,
        "deployment_id": "paper-binding-fixture",
        "owner_attestation_reference": REFERENCE,
    }
    values.update(changes)
    return PaperDeploymentBinding(**values)


@pytest.mark.parametrize("changes", [
    {"account_id": "not-a-uuid"},
    {"deployment_id": "unsafe deployment"},
    {"owner_attestation_reference": ""},
    {"owner_attestation_reference": "decision-271"},
    {"owner_attestation_reference": "owner-attestation:x"},
])
def test_binding_requires_account_deployment_and_external_attestation_reference(changes):
    with pytest.raises(PaperDeploymentBindingError) as caught:
        binding(**changes)
    assert caught.value.__context__ is None


def test_binding_requires_exact_local_identity_and_sanitizes_rejection():
    configured = binding()
    with pytest.raises(PaperDeploymentBindingError) as caught:
        configured.require_match(
            account_id="0ca07231-9205-48f0-9fb5-8e04ae3121be",
            deployment_id="paper-binding-fixture",
        )
    assert ACCOUNT not in str(caught.value) + repr(caught.value)

    with pytest.raises(PaperDeploymentBindingError) as caught:
        configured.require_match(account_id=UNTRUSTED, deployment_id=UNTRUSTED)
    assert UNTRUSTED not in str(caught.value) + repr(caught.value)


def test_binding_requires_the_same_external_attestation_reference():
    with pytest.raises(PaperDeploymentBindingError):
        binding().require_same(binding(owner_attestation_reference="owner-attestation:other-paper-record"))

"""Explicit opt-in only; never collected by the default tests directory."""
import os
import pytest
from eryma import Eryma, presets
from eryma.adapters import JevAdapter, LayaAdapter, VonAdapter, HuggingFaceAdapter

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get("ERYMA_RUN_INTEGRATION") != "1", reason="Real integrations require explicit opt-in")]


def configured(name):
    value = os.environ.get(name)
    if not value:
        pytest.skip("Set the documented integration model variable")
    return value


def assert_engine_contract(model):
    guard = Eryma(decision_model=model)
    for result in (guard.scan_input("How can I contact support?"),
                   guard.scan_output("Please contact the support desk.")):
        assert result.status != "evaluation_error"
        assert isinstance(result.allowed, bool)


def test_real_jev():
    with JevAdapter(model=configured("ERYMA_JEV_MODEL")) as model:
        assert_engine_contract(model)


def test_real_laya():
    with LayaAdapter(model=configured("ERYMA_LAYA_MODEL"),
            backend=os.environ.get("ERYMA_LAYA_BACKEND", "torch"),
            device=os.environ.get("ERYMA_DEVICE", "cpu")) as model:
        assert_engine_contract(model)


def test_real_von():
    with VonAdapter(model=configured("ERYMA_VON_MODEL"),
                    device=os.environ.get("ERYMA_DEVICE", "cpu")) as model:
        assert_engine_contract(model)


def test_real_huggingface():
    check = presets.binary_check("injection", "Detect prompt injection in the input")
    with HuggingFaceAdapter(model=configured("ERYMA_HF_MODEL"), check=check,
            label_mapping={"SAFE":"no_violation", "INJECTION":"violation"},
            device=os.environ.get("ERYMA_DEVICE", "cpu"), local_files_only=True) as model:
        result = Eryma(decision_model=model, input_checks=[check], output_guard=False).scan_input("Hello")
        assert result.status != "evaluation_error"

"""Completeness controls: mocked transports and runtimes only."""
import json

import httpx
import pytest

from eryma import Action, Eryma, EvaluationError, GuardPolicy, ScoreDistribution
from eryma.adapters import JevAdapter, LayaAdapter, VonAdapter
from eryma.adapters.decisions_api import DecisionsAPIFormat
from eryma.adapters.errors import InvalidOutputError
from eryma.adapters.http import HTTPDecisionModel, ProviderError
from test_native_adapters import answers, request, install_laya, install_von

INCOMPLETE = [
    {"usage": {"truncated": True}},
    {"usage": {"state_tokens_dropped": 1}},
    {"usage": {"options": {"classification": {"collapsed": True}}}},
    {"truncation": {"reason": "PRIVATE_DETAIL"}},
]


def generic(metadata, calls):
    wire = DecisionsAPIFormat(model="TEST_ONLY")
    def handler(req):
        calls.append(req)
        payload = json.loads(req.content)
        return httpx.Response(200, json={**answers(payload["questions"]), **metadata})
    return HTTPDecisionModel(endpoint="https://decision.example/evaluate",
        api_key="TEST_ONLY", request_builder=wire.build_request,
        response_parser=wire.parse_response, transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("guard", ["input", "output"])
@pytest.mark.parametrize("metadata", INCOMPLETE)
def test_generic_incomplete_is_not_an_allow(guard, metadata):
    calls = []
    with generic(metadata, calls) as model:
        result = getattr(Eryma(decision_model=model), "scan_" + guard)("PRIVATE_TEXT")
        assert result.status == "evaluation_error"
        assert result.action == Action.BLOCK and not result.allowed
        assert all(c.selected_decision is None and not c.scores for c in result.checks)
        with pytest.raises(ProviderError) as exc:
            model.evaluate(request(guard))
    assert len(calls) == 2
    assert "PRIVATE" not in repr(result) + str(exc.value)


@pytest.mark.parametrize("guard", ["input", "output"])
@pytest.mark.parametrize("metadata", INCOMPLETE)
def test_direct_formatter_rejects_incomplete(guard, metadata):
    req = request(guard)
    wire = DecisionsAPIFormat(model="TEST_ONLY")
    payload = wire.build_request(req)
    with pytest.raises(ValueError, match="Incomplete or invalid decisions response"):
        wire.parse_response({**answers(payload["questions"]), **metadata}, req)


@pytest.mark.parametrize("metadata", [
    {}, {"usage": None}, {"usage": {}}, {"usage": []},
    {"usage": {"truncated": False, "state_tokens_dropped": 0, "options": {}}, "truncation": None},
    {"usage": {"input_tokens": 10, "output_tokens": 2}},
])
@pytest.mark.parametrize("guard", ["input", "output"])
def test_complete_controls_keep_scores(guard, metadata):
    with generic(metadata, []) as model:
        result = getattr(Eryma(decision_model=model), "scan_" + guard)("Hello")
    assert result.status == "evaluated" and result.allowed
    assert result.checks[0].confidence == (1 if guard == "input" else .9)


@pytest.mark.parametrize("usage", ["PRIVATE_DETAIL", ["PRIVATE_DETAIL"], 1, True])
def test_truthy_malformed_usage_rejected(usage):
    with generic({"usage": usage}, []) as model:
        result = Eryma(decision_model=model).scan_input("Hello")
    assert result.status == "evaluation_error" and not result.allowed
    assert "PRIVATE" not in repr(result)


@pytest.mark.parametrize("guard", ["input", "output"])
@pytest.mark.parametrize("action", list(Action))
def test_explicit_failure_actions_preserved(guard, action):
    policy = GuardPolicy(failure_action=action)
    with generic(INCOMPLETE[0], []) as model:
        sdk = Eryma(decision_model=model, input_policy=policy, output_policy=policy)
        if action == Action.RAISE_ERROR:
            with pytest.raises(EvaluationError) as exc:
                getattr(sdk, "scan_" + guard)("PRIVATE_TEXT")
            result = exc.value.result
        else:
            result = getattr(sdk, "scan_" + guard)("PRIVATE_TEXT")
    assert result.status == "evaluation_error" and result.action == action
    assert result.allowed == (action in (Action.ALLOW, Action.FLAG))
    assert result.flagged == (action == Action.FLAG)
    assert "PRIVATE" not in repr(result)


@pytest.mark.parametrize("input_on,output_on", [(False, False), (False, True), (True, False)])
def test_disabled_guard_never_parses(input_on, output_on):
    calls = []
    with generic(INCOMPLETE[0], calls) as model:
        sdk = Eryma(decision_model=model, input_guard=input_on, output_guard=output_on)
        for guard, enabled in (("input", input_on), ("output", output_on)):
            if not enabled:
                result = getattr(sdk, "scan_" + guard)("Hello")
                assert result.status == "skipped" and result.allowed
    assert not calls


def test_arbitrary_http_parser_owns_its_metadata():
    def parse(data, req):
        return {c.name: ScoreDistribution({k: float(i == 0) for i, k in enumerate(c.criteria)})
                for c in req.checks}
    with HTTPDecisionModel(endpoint="https://custom.example/evaluate",
        request_builder=lambda req: {}, response_parser=parse,
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={
            "usage": "CUSTOM_SCHEMA", "truncation": "NOT_DECISIONS_API"}))) as model:
        assert Eryma(decision_model=model).scan_input("Hello").allowed


@pytest.mark.parametrize("guard", ["input", "output"])
@pytest.mark.parametrize("metadata", INCOMPLETE)
@pytest.mark.parametrize("kind", ["jev", "laya", "von"])
def test_native_completeness_and_sanitized_error_unchanged(monkeypatch, guard, metadata, kind):
    req = request(guard)
    wire = DecisionsAPIFormat(model="TEST_ONLY")
    payload = {**answers(wire.build_request(req)["questions"]), **metadata}
    if kind == "jev":
        model = JevAdapter(model="TEST_ONLY", api_key="TEST_ONLY",
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))
    elif kind == "laya":
        runtime, _ = install_laya(monkeypatch)
        runtime.payload = payload
        model = LayaAdapter()
    else:
        engines = install_von(monkeypatch)
        model = VonAdapter()
        engines[0].payload = payload
    with model:
        with pytest.raises(InvalidOutputError) as exc:
            model.evaluate(req)
        result = getattr(Eryma(decision_model=model), "scan_" + guard)("PRIVATE_TEXT")
    assert not result.allowed and result.status == "evaluation_error"
    assert "PRIVATE" not in str(exc.value) + repr(result)


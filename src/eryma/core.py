"""Middleware only: never invokes the protected language model."""
from __future__ import annotations
from copy import deepcopy
import json
from typing import Sequence
from . import presets
from .decisions import default_aggregate, evaluate_check
from .types import (Action, Aggregator, Check, CheckResult, DecisionModel, EvaluationError,
                    EvaluationRequest, GuardPolicy, SecurityResult, finite_number)


def _optional_text(value, name):
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{name} must be non-empty text or None")
    return value


def _json_copy(value, name):
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError(f"{name} must contain finite JSON data") from None


class Eryma:
    def __init__(self, *, decision_model: DecisionModel | None = None,
                 objective: str | None = None, security_policy: str | None = None,
                 input_guard: bool = True, output_guard: bool = True,
                 input_threshold: float | None = None, output_threshold: float | None = None,
                 input_checks: Sequence[Check] | None = None, output_checks: Sequence[Check] | None = None,
                 input_policy: GuardPolicy | None = None, output_policy: GuardPolicy | None = None,
                 input_aggregator: Aggregator | None = None, output_aggregator: Aggregator | None = None):
        if type(input_guard) is not bool or type(output_guard) is not bool:
            raise ValueError("Guard switches must be booleans")
        if (input_guard or output_guard) and not callable(getattr(decision_model, "evaluate", None)):
            raise ValueError("Enabled guards require a decision model with evaluate(request)")
        self._model = decision_model
        self._objective = _optional_text(objective, "objective")
        self._security_policy = _optional_text(security_policy, "security_policy")
        self._enabled = {"input": input_guard, "output": output_guard}
        self._thresholds, self._checks, self._policies, self._aggregators = {}, {}, {}, {}
        configs = (("input", input_threshold, input_checks, input_policy, input_aggregator, presets.input_checks),
                   ("output", output_threshold, output_checks, output_policy, output_aggregator, presets.output_checks))
        for guard, threshold, checks, policy, aggregator, defaults in configs:
            if threshold is not None:
                threshold = finite_number(threshold)
                if not 0 <= threshold <= 1:
                    raise ValueError("Thresholds must be in [0, 1]")
            self._thresholds[guard] = threshold
            checks = tuple(defaults() if checks is None else checks)
            if any(not isinstance(c, Check) for c in checks):
                raise ValueError("Checks must be Check objects")
            if len({c.name for c in checks}) != len(checks):
                raise ValueError("Check names must be unique within a guard")
            if self._enabled[guard]:
                if not checks:
                    raise ValueError("An enabled guard requires at least one check")
                if any(c.requires_objective for c in checks) and self._objective is None:
                    raise ValueError("Scope-dependent checks require an objective")
            self._checks[guard] = tuple(Check(c.name, c.instructions, c.criteria, c.actions, c.kind,
                                             c.requires_objective, c.requires_references) for c in checks)
            if policy is not None and not isinstance(policy, GuardPolicy):
                raise ValueError("Use GuardPolicy for enforcement configuration")
            if aggregator is not None and not callable(aggregator):
                raise ValueError("Aggregator must be callable")
            self._policies[guard] = policy or GuardPolicy()
            self._aggregators[guard] = aggregator or default_aggregate

    def scan_input(self, text: str, *, trusted_references: dict | None = None,
                   external_content: object = None) -> SecurityResult:
        return self._scan("input", text, None, trusted_references, external_content)

    def scan_output(self, text: str, *, user_prompt: str | None = None,
                    trusted_references: dict | None = None, external_content: object = None) -> SecurityResult:
        return self._scan("output", text, user_prompt, trusted_references, external_content)

    def _scan(self, guard, text, user_prompt, references, external):
        if not self._enabled[guard]:
            return SecurityResult(guard, "skipped", Action.ALLOW, True, False)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Text must be non-empty")
        _optional_text(user_prompt, "user_prompt")
        if references is not None and not isinstance(references, dict):
            raise ValueError("trusted_references must be a JSON object")
        references = _json_copy(references or {}, "trusted_references")
        external = _json_copy(external, "external_content")
        checks = self._checks[guard]
        if any(c.requires_references for c in checks) and not references:
            raise ValueError("This evaluation requires nonempty trusted references")
        untrusted = {"user_message": text} if guard == "input" else {"llm_response": text, "user_message": user_prompt}
        untrusted["external_content"] = external
        request = EvaluationRequest(guard, {"objective": self._objective,
            "security_policy": self._security_policy, "references": references}, untrusted, deepcopy(checks))
        policy, threshold = self._policies[guard], self._thresholds[guard]
        try:
            distributions = self._model.evaluate(request)
            if not isinstance(distributions, dict) and not hasattr(distributions, "keys"):
                raise ValueError()
            if set(distributions) != {c.name for c in checks}:
                raise ValueError()
        except Exception:
            results = tuple(self._error_check(c, threshold, policy, "model_error") for c in checks)
            return self._finish(guard, results)
        results = []
        for check in checks:
            try:
                results.append(evaluate_check(check, distributions[check.name], threshold, policy))
            except Exception:
                results.append(self._error_check(check, threshold, policy, "invalid_scores"))
        return self._finish(guard, tuple(results))

    @staticmethod
    def _error_check(check, threshold, policy, code):
        return CheckResult(check.name, None, None, {}, None, (), threshold, None,
                           "evaluation_error", policy.failure_action, code)

    def _finish(self, guard, results):
        error = None
        try:
            action = Action(self._aggregators[guard](deepcopy(results)))
        except Exception:
            action = self._policies[guard].failure_action
            error = "aggregation_error"
        statuses = {r.status for r in results}
        status = next((s for s in ("evaluation_error", "tie", "insufficient_confidence") if s in statuses), "evaluated")
        if error:
            status = "evaluation_error"
        result = SecurityResult(guard, status, action, action in (Action.ALLOW, Action.FLAG),
                                action == Action.FLAG or any(r.action == Action.FLAG for r in results), results, error)
        if action == Action.RAISE_ERROR:
            raise EvaluationError(result) from None
        return result

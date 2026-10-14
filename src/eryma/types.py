"""Provider-neutral contracts. Payload reprs omit application data."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Mapping, Protocol
import math
import re


class Action(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    FLAG = "flag"
    RAISE_ERROR = "raise_error"


class ScoreKind(str, Enum):
    PROBABILITY = "probability"
    UNIT_INTERVAL = "unit_interval"  # Meaningful threshold scale, not calibrated probability.
    COMPARABLE = "comparable"  # Ranking only; numerical thresholds unsupported.


def finite_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a finite numeric score")
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise ValueError("Expected a finite numeric score") from None
    if not math.isfinite(result):
        raise ValueError("Expected a finite numeric score")
    return result


@dataclass(frozen=True)
class Check:
    name: str
    instructions: str = field(repr=False)
    criteria: Mapping[str, str] = field(repr=False)
    actions: Mapping[str, Action]
    kind: str = "multiclass"
    requires_objective: bool = False
    requires_references: bool = False

    def __post_init__(self):
        if not isinstance(self.name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ValueError("Check name must be a lowercase identifier")
        if not isinstance(self.instructions, str) or not self.instructions.strip():
            raise ValueError("Check instructions must be non-empty")
        if self.kind not in ("multiclass", "binary"):
            raise ValueError("Check kind must be multiclass or binary")
        criteria = dict(self.criteria)
        if len(criteria) < 2 or any(not isinstance(k, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", k)
                                    or not isinstance(v, str) or not v.strip() for k, v in criteria.items()):
            raise ValueError("Provide at least two named criteria with descriptions")
        if self.kind == "binary" and set(criteria) != {"violation", "no_violation"}:
            raise ValueError("Binary criteria must be violation and no_violation")
        if set(self.actions) != set(criteria):
            raise ValueError("Each category requires an explicit action")
        if type(self.requires_objective) is not bool or type(self.requires_references) is not bool:
            raise ValueError("Context requirements must be booleans")
        object.__setattr__(self, "criteria", criteria)
        object.__setattr__(self, "actions", {k: Action(v) for k, v in self.actions.items()})


@dataclass(frozen=True)
class EvaluationRequest:
    guard: str
    trusted_context: dict = field(repr=False)
    untrusted_data: dict = field(repr=False)
    checks: tuple[Check, ...] = field(repr=False)


@dataclass(frozen=True)
class ScoreDistribution:
    scores: Mapping[str, float] = field(repr=False)
    kind: ScoreKind = ScoreKind.PROBABILITY


class DecisionModel(Protocol):
    def evaluate(self, request: EvaluationRequest) -> Mapping[str, ScoreDistribution]: ...


@dataclass(frozen=True)
class GuardPolicy:
    tie_action: Action = Action.BLOCK
    low_confidence_action: Action = Action.BLOCK
    failure_action: Action = Action.BLOCK

    def __post_init__(self):
        for name in ("tie_action", "low_confidence_action", "failure_action"):
            object.__setattr__(self, name, Action(getattr(self, name)))


@dataclass(frozen=True)
class CheckResult:
    name: str
    selected_decision: str | None
    confidence: float | None
    scores: dict[str, float]
    score_kind: str | None
    tied_decisions: tuple[str, ...]
    threshold: float | None
    threshold_met: bool | None
    status: str
    action: Action
    error: str | None = None


@dataclass(frozen=True)
class SecurityResult:
    guard: str
    status: str
    action: Action
    allowed: bool
    flagged: bool
    checks: tuple[CheckResult, ...] = ()
    error: str | None = None

    def _single(self, name):
        return getattr(self.checks[0], name) if len(self.checks) == 1 else None

    @property
    def selected_decision(self): return self._single("selected_decision")
    @property
    def confidence(self): return self._single("confidence")
    @property
    def scores(self): return self._single("scores")
    @property
    def threshold(self): return self._single("threshold")
    @property
    def threshold_met(self): return self._single("threshold_met")
    @property
    def tied_decisions(self): return self._single("tied_decisions")

    def to_dict(self) -> dict:
        from dataclasses import asdict
        result = asdict(self)
        result["action"] = self.action.value
        for check in result["checks"]:
            check["action"] = check["action"].value
        for name in ("selected_decision", "confidence", "scores", "threshold", "threshold_met", "tied_decisions"):
            result[name] = getattr(self, name)
        return result


class EvaluationError(RuntimeError):
    """Requested RAISE_ERROR enforcement; carries sanitized diagnostics."""
    def __init__(self, result: SecurityResult):
        super().__init__("Eryma evaluation requires application handling")
        self.result = result


Aggregator = Callable[[tuple[CheckResult, ...]], Action]

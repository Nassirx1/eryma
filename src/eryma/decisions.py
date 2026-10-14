"""Independent score validation, selection, threshold and action stages."""
from .types import Action, Check, CheckResult, GuardPolicy, ScoreDistribution, ScoreKind, finite_number


def validate_scores(check: Check, distribution: ScoreDistribution) -> tuple[dict, ScoreKind]:
    if not isinstance(distribution, ScoreDistribution):
        raise ValueError("Invalid decision distribution")
    kind = ScoreKind(distribution.kind)
    if set(distribution.scores) != set(check.criteria):
        raise ValueError("Missing or unexpected decision categories")
    scores = {k: finite_number(distribution.scores[k]) for k in check.criteria}
    if kind != ScoreKind.COMPARABLE and any(not 0 <= v <= 1 for v in scores.values()):
        raise ValueError("Expected scores in [0, 1]")
    if kind == ScoreKind.PROBABILITY and abs(sum(scores.values()) - 1) > .02:
        raise ValueError("Invalid probability sum")
    return scores, kind


def select_highest(scores: dict[str, float]) -> tuple[str | None, float, tuple[str, ...]]:
    confidence = max(scores.values())
    winners = tuple(sorted(k for k, v in scores.items() if v == confidence))
    return (winners[0], confidence, ()) if len(winners) == 1 else (None, confidence, winners)


def threshold_satisfied(confidence: float, threshold: float | None, kind: ScoreKind) -> bool:
    if threshold is None:
        return True
    if kind == ScoreKind.COMPARABLE:
        raise ValueError("This score scale does not support thresholds")
    return confidence >= threshold


def evaluate_check(check: Check, distribution: ScoreDistribution, threshold: float | None,
                   policy: GuardPolicy) -> CheckResult:
    scores, kind = validate_scores(check, distribution)
    winner, confidence, ties = select_highest(scores)
    met = threshold_satisfied(confidence, threshold, kind)
    if ties:
        status, action = "tie", policy.tie_action
    elif not met:
        status, action = "insufficient_confidence", policy.low_confidence_action
    else:
        status, action = "evaluated", check.actions[winner]
    return CheckResult(check.name, winner, confidence, scores, kind.value, ties, threshold, met, status, action)


def default_aggregate(results: tuple[CheckResult, ...]) -> Action:
    precedence = (Action.RAISE_ERROR, Action.BLOCK, Action.FLAG, Action.ALLOW)
    return next(action for action in precedence if any(r.action == action for r in results))

"""Offline contract demo with fixed scores; this is not a security detector."""
from eryma import Eryma, ScoreDistribution


class CustomDecisionModel:
    def evaluate(self, request):
        return {check.name: ScoreDistribution({category:float(category in ("safe", "no_violation"))
                for category in check.criteria}) for check in request.checks}


if __name__ == "__main__":
    guard = Eryma(decision_model=CustomDecisionModel())
    print(guard.scan_input("Where is the support desk?").to_dict())

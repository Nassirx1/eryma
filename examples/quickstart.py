"""Offline integration demo. The fixed decision scores are NOT a security detector."""
from eryma import Eryma, ScoreDistribution


class DemoDecisionModel:
    def evaluate(self, request):
        return {c.name: ScoreDistribution({k: float(k in ('safe','no_violation'))
                                          for k in c.criteria}) for c in request.checks}


def main():
    guard=Eryma(decision_model=DemoDecisionModel())
    prompt='How can I contact support?'
    if not guard.scan_input(prompt).allowed:
        return
    # Your application calls its own LLM here, without passing that client to Eryma.
    response='Please contact the support desk.'
    result=guard.scan_output(response,user_prompt=prompt)
    if result.allowed:
        print(response)


if __name__=='__main__':
    main()

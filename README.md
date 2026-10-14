# ERYMA

Lightweight, model-agnostic Python security middleware. **You run your LLM. Eryma evaluates only the inputs and outputs you explicitly pass to it.** There is no protected-model client, inference call, mandatory provider, or built-in API credential.

## Install

Python 3.10+. Version 0.2.0 is a local prerelease, not published to PyPI. From this directory:

```sh
python -m pip install .
# Only if you want the optional generic HTTP transport:
python -m pip install '.[http]'
```

The distribution and Python import are both `eryma`. After publication, installation will be `pip install eryma`; package-name availability has not been verified.

## Use your own decision model

Any local, cloud, self-hosted or custom decision model can implement `evaluate(request)`. It receives an `EvaluationRequest` and returns a mapping from each check name to a `ScoreDistribution`. No particular model or provider is required.

```python
from eryma import Eryma

guard = Eryma(
    decision_model=my_decision_model,  # Your adapter implementing evaluate(request).
    objective="This assistant answers banking support questions but cannot execute transactions.",
    security_policy="Do not disclose confidential information.",
    input_guard=True,
    output_guard=True,
    input_threshold=None,
    output_threshold=None,
)

input_result = guard.scan_input(user_prompt)
if input_result.allowed:
    response = my_llm.generate(user_prompt)  # Your application, not Eryma.
    output_result = guard.scan_output(response, user_prompt=user_prompt)
    if output_result.allowed:
        print(response)
```

This integration snippet assumes your existing application defines `my_decision_model`, `my_llm` and `user_prompt`. See [the runnable offline example](examples/quickstart.py). Its fixed scores illustrate wiring, **not real threat detection**.

Call either scan independently, in either order. A blocked input does not automatically stop your application: you must inspect `allowed` before calling your model. Buffer your model's answer and check output before displaying it. Eryma does not retroactively protect already streamed text or undo side effects.

## Objective, policy, and checks

`objective` describes the application's purpose and operational limits. `security_policy` describes restrictions. Both are optional, trusted initialization-time text, logically separate from untrusted content. No default objective is invented.

Default input checks classify `safe`, `prompt_injection`, `jailbreak`, or `harmful_request`. Default output checks independently evaluate harmful content and instruction overrides. These replaceable presets **do not automatically enforce application scope**. Ordinary out-of-scope requests are not necessarily injection.

Add explicit application-specific checks:

```python
from eryma import Eryma, presets

guard = Eryma(
    decision_model=my_decision_model,
    objective="Banking support only; no transaction execution.",
    security_policy="Never disclose customer account details.",
    input_checks=(*presets.input_checks(), presets.scope_check()),
    output_checks=(
        *presets.output_checks(),
        presets.scope_check(),
        presets.confidentiality_check(),
        presets.grounded_claims_check(),
    ),
)
result = guard.scan_output(
    response,
    user_prompt=user_prompt,
    trusted_references={"authorized_actions": [], "verified_facts": {"support_hours": "09:00–17:00"}},
    external_content={"retrieved_document": untrusted_document},
)
```

An enabled `requires_objective=True` check requires a nonempty objective. A `requires_references=True` check requires nonempty trusted references for that scan. Invalid trusted configuration raises `ValueError`; Eryma never guesses missing scope. A confidentiality check needs meaningful confidential-data rules in your policy or references; do not supply live credentials as test secrets.

Trusted context contains objective, policy and references. Untrusted data separately contains user messages, LLM responses and external content. Decision adapters must preserve that separation. Never put user-provided text in trusted fields.

Define any categories or independent binary checks with `Check(name, instructions, criteria, actions, kind=...)`. Each category needs an explicit `Action` mapping. Multiclass checks use arbitrary lowercase category identifiers. Binary checks use `violation` and `no_violation`. Input and output lists replace their defaults, not append to them; use presets explicitly when extending.

## Selection and thresholds

1. Validate the adapter's score distribution.
2. Select the unique highest-scoring category.
3. Evaluate the optional guard-specific threshold.
4. Apply the check's action mapping or exceptional-outcome policy.
5. Combine per-check actions.

Both thresholds default to `None`. A safe score of 0.30 wins if every other category is lower. No category receives priority because of its name. Equality to a configured threshold passes. Threshold failure keeps the selected category and score, sets `insufficient_confidence`, and applies the low-confidence action.

Exact score ties have no selected category; sorted tied labels are returned. Ties use the tie policy, never dictionary order. If a tied score also misses the threshold, the tie policy takes precedence while `threshold_met` records the comparison.

```python
from eryma import Action, GuardPolicy

guard = Eryma(
    decision_model=my_decision_model,
    input_threshold=0.85,
    output_threshold=None,
    input_policy=GuardPolicy(low_confidence_action=Action.FLAG),
    output_policy=GuardPolicy(failure_action=Action.BLOCK),
)
```

Each guard independently supports `tie_action`, `low_confidence_action`, and `failure_action`. All default to BLOCK.

| Action | allowed | Meaning |
|---|---|---|
| ALLOW | true | Continue |
| BLOCK | false | Stop |
| FLAG | true | Continue with a warning indicator |
| RAISE_ERROR | false | Raise typed EvaluationError carrying sanitized result |

Default aggregation prioritizes RAISE_ERROR, BLOCK, FLAG, ALLOW. Any accepted violation mapped to BLOCK therefore blocks. Thresholds apply to each independent check's winning score, not an average. A custom `input_aggregator` or `output_aggregator` receives the individual CheckResults and returns an Action. It can explicitly override individual actions, including failures, so treat it as trusted security-critical code. Aggregator exceptions/invalid actions use the guard's failure policy.

## Adapter contract and score semantics

```python
from eryma import ScoreDistribution, ScoreKind

class MyDecisionAdapter:
    def evaluate(self, request):
        # Call your local or remote decision model using request.trusted_context,
        # request.untrusted_data, request.guard and request.checks.
        model_results = your_evaluator(request)
        return {
            check.name: ScoreDistribution(
                scores=model_results[check.name],
                kind=ScoreKind.PROBABILITY,
            )
            for check in request.checks
        }
```

Return exactly the requested checks and categories. Missing/extra names, malformed results, booleans, strings, NaN and infinity are evaluation errors. Eryma never manufactures missing confidence scores or silently normalizes arbitrary values.

- `PROBABILITY`: values in [0,1], sum within 0.02 of 1 to allow rounding; no renormalization. Threshold comparison supported. Declaring this does not prove empirical calibration.
- `UNIT_INTERVAL`: comparable scores in [0,1] with adapter-declared meaningful threshold comparison; not claimed to be probabilities.
- `COMPARABLE`: finite numeric ranking scores, including negative values. Thresholds unsupported; configuring a threshold produces an explicit evaluation error under the failure policy.

For independent binary probabilities, adapters may derive the complementary score only when the provider defines that probability semantics. Do not convert logits into claimed probabilities without a justified adapter transformation.

## Optional HTTP transport

The HTTP adapter has **no default endpoint, request schema, model identifier or provider**. Supply both translation functions:

```python
from eryma.adapters.http import HTTPDecisionModel

with HTTPDecisionModel(
    endpoint=your_decision_endpoint,
    api_key=your_decision_api_key,  # Optional bearer authentication.
    request_builder=build_provider_request,  # EvaluationRequest -> JSON object.
    response_parser=parse_provider_response,  # (JSON object, request) -> named ScoreDistributions.
) as model:
    guard = Eryma(decision_model=model)
    result = guard.scan_input(user_prompt)
```

For another authentication scheme use `headers={...}`; do not supply a custom Authorization header together with `api_key`. Standard HTTP transport requires HTTPS, disables redirects, sanitizes errors, and performs no automatic retries. Host proxy/CA settings may affect transport. Local models need no HTTP transport at all; implement `evaluate` directly, including through your own local client.

An optional `DecisionsAPIFormat(model=your_model_id)` helper provides `build_request` and `parse_response` for providers supporting state/questions with choice/noul answers, including Jev. It neither selects nor connects to a provider. Set your endpoint and model explicitly. Choice probabilities remain a multiclass distribution; each noul value becomes its own violation/no_violation distribution. Other providers use their own translation functions, not this format by assumption.

## Structured results

`SecurityResult` exposes `guard`, `status`, `action`, `allowed`, `flagged`, `checks`, and optional sanitized `error`. Per-check results include scores and score kind, selected decision, winning confidence, tied labels, threshold, threshold satisfaction, status and action. Single-check results expose decision fields directly; multi-check aggregate confidence/decision fields are None.

Statuses: `evaluated`, `tie`, `insufficient_confidence`, `evaluation_error`, `skipped`. Aggregate status prioritizes evaluation_error, tie, insufficient_confidence, then evaluated. Classification remains separate from enforcement: an evaluated threat can be explicitly mapped to FLAG, while a selected safe decision can be blocked for insufficient confidence.

With no threshold, an evaluated check reports `threshold_met=True`. Unevaluated/error checks use None. Use `result.to_dict()` for JSON-serializable diagnostics. `EvaluationError.result` carries the same diagnostics for RAISE_ERROR. Raw prompts, answers, references, credentials and provider exception text are not included; category/check names are developer-controlled identifiers. No default logging or telemetry occurs.

## Independent switches

| input_guard | output_guard | Protection |
|---|---|---|
| true | true | Both scan methods active, independently |
| true | false | Input scans only |
| false | true | Output scans only |
| false | false | No Eryma protection; no decision model required |

Disabled methods immediately return skipped/allow without validating scan payloads or calling a model. There are no hidden guards.

## Development and limits

```sh
python -m pip install -e '.[dev]'
python -m pytest
python -m build --outdir dist/eryma-0.2.0
```

Synchronous, single-turn, text-only middleware. No managed inference, streaming interception, tools, autonomous actions or protection of content not submitted. Enforce application authorization, data minimization, request-size/rate limits and safe rendering separately. Decide what data your decision provider is permitted to receive. Disabling guards or selecting ALLOW/FLAG on failures weakens protection.

The earlier supermarket garak results and SDK security-review draft do not evaluate ERYMA 0.2.0. Tests use mocked models and establish software behavior, not real-world detection accuracy. See [migration](MIGRATION.md) and [contributing](CONTRIBUTING.md). MIT licensed. This version has not been published to PyPI.

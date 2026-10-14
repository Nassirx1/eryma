# Contributing to ERYMA

Install `.[dev]` and run `python -m pytest`. Default tests must be offline and must not require credentials or incur charges.

Adapters implement `DecisionModel.evaluate(EvaluationRequest)` and return named ScoreDistributions. They may use local, self-hosted or cloud models. Document score meaning and threshold support; preserve the separation of trusted context from untrusted content. HTTP integrations should use configurable wire translators rather than adding mandatory provider dependencies.

Keep selection, threshold evaluation, action mapping and aggregation separate. Add regression tests for missing/malformed decisions, exact ties, failures, independent configurations and sensitive-data suppression. Never introduce protected-LLM inference methods or hidden guards.

Discuss breaking API changes before implementation. Do not include credentials, customer prompts, or raw outputs in issues or fixtures. Publishing is a separate maintainer action; the test workflow has no publishing privileges.

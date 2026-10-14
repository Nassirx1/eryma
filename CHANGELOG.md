# Release notes

## 0.3.0 — Native decision-model integrations

- Add lazy Jev, local Laya (torch/MLX), local Von, and fixed-category Hugging Face adapters under the common DecisionModel contract.
- Add optional jev/laya/von/mlx/huggingface installation extras; core dependencies remain empty. Published upstream packages are pinned for Laya/Von/MLX integration compatibility.
- Jev uses the documented Decisions API, explicit model selection and optional environment credentials. Cloud reference transmission requires explicit opt-in. No silent request retry.
- Preserve named choice probabilities and independent binary probabilities. Von uses noul_raw instead of its committed band; incomplete/truncated local evaluations are rejected.
- Add sanitized adapter-error types, context-manager cleanup, runnable examples, mocked unit tests and separate explicit-opt-in integration smoke tests.
- Hugging Face support is limited to explicitly mapped single-label input classifiers. It does not evaluate arbitrary objectives, policies, output safety, or references. No generative or multilabel adapter is supplied.
- MLX requires compatible Apple Silicon/macOS/Python. Von requires Python 3.12 and currently supports its upstream model aliases, not arbitrary Hub identifiers.

Existing middleware, generic HTTP/DecisionsAPIFormat, custom adapters, check presets, action aggregation, ties, failure policies and independent thresholds remain unchanged. No protected-model invocation was added. Native classes are additive; existing custom/generic integrations require no migration. Version 0.3.0 is prepared locally; real weights/API compatibility was researched and mocked but not exercised against paid services or downloaded models. No automatic publication, deployment or release was performed.

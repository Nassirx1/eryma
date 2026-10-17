# Release notes

## 0.3.1 — Consistent incomplete-evaluation rejection

- Fix generic HTTP + DecisionsAPIFormat accepting otherwise valid scores when the provider explicitly reports truncation, dropped state tokens or collapsed options.
- Share the format-owned completeness check with native Jev/Laya/Von adapters, preserving sanitized errors and score validation.
- Preserve custom HTTP schemas, middleware APIs, thresholds, disabled guards and explicit developer failure-policy overrides.
- Add 68 offline regression cases for input/output, direct parsing, native integrations, valid responses and failure policies. No model weights or paid API calls are required.

## 0.3.0 — Native decision-model integrations

- Add lazy Jev, local Laya (torch/MLX), local Von, and fixed-category Hugging Face adapters under the common DecisionModel contract.
- Add optional jev/laya/von/mlx/huggingface installation extras; core dependencies remain empty. Published upstream packages are pinned for Laya/Von/MLX integration compatibility.
- Jev uses the documented Decisions API, explicit model selection and optional environment credentials. Cloud reference transmission requires explicit opt-in. No silent request retry.
- Preserve named choice probabilities and independent binary probabilities. Von uses noul_raw instead of its committed band; incomplete/truncated local evaluations are rejected.
- Add sanitized adapter-error types, context-manager cleanup, runnable examples, mocked unit tests and separate explicit-opt-in integration smoke tests.
- Hugging Face support is limited to explicitly mapped single-label input classifiers. It does not evaluate arbitrary objectives, policies, output safety, or references. No generative or multilabel adapter is supplied.
- MLX requires compatible Apple Silicon/macOS/Python. Von requires Python 3.12 and currently supports its upstream model aliases, not arbitrary Hub identifiers.

Existing middleware, generic HTTP/DecisionsAPIFormat, custom adapters, check presets, action aggregation, ties, failure policies and independent thresholds remain unchanged. No protected-model invocation was added. Native classes are additive; existing custom/generic integrations require no migration. Version 0.3.0 is prepared locally; real weights/API compatibility was researched and mocked but not exercised against paid services or downloaded models. No automatic publication, deployment or release was performed.

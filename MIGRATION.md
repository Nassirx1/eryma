# Migration from llm_security 0.1 to eryma 0.2

This is a breaking, unpublished local release. Install into a fresh virtual environment; do not assume an existing installation of the old distribution will be replaced by a differently named package.

- Distribution and import are now `eryma`. Remove old `llm_security` imports.
- `GuardedChat`, its `chat()` method, protected model callbacks and `OpenAICompatible` are removed, without compatibility aliases. Your application owns inference and credentials.
- Replace `Policy(instructions)` with separate optional `objective` and `security_policy` initialization fields.
- Use `scan_input()` before your own inference and `scan_output()` before displaying its result. Both are independent; you must enforce each returned action.
- Replace `trusted_context` with `trusted_references`; pass retrieved/external material through `external_content`, not trusted fields.
- Use any adapter implementing `evaluate(request)`. The old `Jev` convenience client is removed; the optional generic HTTP transport plus `DecisionsAPIFormat` preserves the original state/questions wire compatibility without choosing a provider or model.
- Input and output criteria are configurable. Defaults are general security checks; add scope, confidentiality or grounded-claims checks explicitly when needed.
- Thresholds default to None. Binary output argmax still blocks a violation winner or a tie by default. Per-check thresholds apply to the winning score, not just the violation score.
- Results contain security decisions, never model responses. `allowed` determines whether the application may continue; FLAG allows with a warning. Failure/tie/low-confidence policies default to BLOCK.
- No protected-model environment variables or default objective are provided. `.[http]` is optional; the core imports without HTTP dependencies.

The old distribution/build copies are not used by the new release. Build only into `dist/eryma-0.2.0` and upload explicitly chosen new artifacts if publication is authorized later. Earlier experiment benchmarks and security-review drafts are not evidence for this refactor.

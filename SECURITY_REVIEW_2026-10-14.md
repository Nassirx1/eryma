# ERYMA 0.2.0 manual security review

Reviewed on 14 October 2026 from the current local source, without the Codex Security plugin. This is a manual source review with offline mocked verification, not a certification or a measurement of decision-model detection accuracy.

## Outcome

No confirmed high- or medium-severity vulnerability, direct guard bypass, or embedded live credential was identified in the reviewed current ERYMA source. Two conditional hardening gaps remain: exception objects retain sensitive context, and HTTP responses have no size ceiling. Neither was demonstrated as an exploit against a deployed application.

## Scope and evidence

Reviewed all current Python modules under `src/eryma`, both test modules, the runnable example, package configuration, CI workflow, README, migration/contribution guidance, security guidance, and empty environment-variable template. Historical build/install copies, generated caches, the original supermarket experiment, and external model/provider implementations are outside this review.

The existing 83 SDK tests passed. Additional in-memory probes used only dummy data and `httpx.MockTransport`; no real credentials, network requests, paid evaluations, or production traffic were used. Those probes verified exception-message/result sanitization and demonstrated retained exception context. Runtime code was not changed.

## Security controls confirmed

- Guard configuration, objectives, policies, references, checks, and action mapping are trusted application configuration. User text, responses, and external content enter a separate untrusted request field. The optional state/questions formatter does not copy untrusted content into its evaluation instructions.
- Default enforcement blocks ties, missing checks/categories, malformed scores, nonfinite numbers, invalid score types, provider failures, and aggregation failures. A single blocking check dominates allow/flag under the default aggregator.
- Incoming adapter data cannot introduce new action mappings or arbitrary categories. Check configuration is copied before evaluation, and request checks are separately copied before invoking adapters.
- Disabled guards, configurable failure actions, low-confidence actions, and custom aggregation can intentionally allow content. These are documented developer choices rather than demonstrated bypasses.
- HTTP destinations come from developer initialization rather than scanned text. The normal adapter requires HTTPS, uses the client's default TLS verification, disables redirects, and supplies no automatic retry loop. Mocked tests establish that a redirect receives only one request.
- Results contain configured identifiers, validated numeric scores, and fixed error codes. Ordinary exception messages and formatted tracebacks suppress raw provider errors. The core contains no logging, telemetry, code execution, file access, or protected-LLM invocation.
- Scope, confidentiality, and reference-grounding checks are opt-in. Supplying an objective or policy does not itself install those checks; this is documented.

## Conditional hardening gap: retained exception context

Locations: `src/eryma/adapters/http.py:61–62` and `src/eryma/core.py:101–103,131`.

Raising a sanitized exception with `from None` hides chaining in ordinary formatted tracebacks, but does not remove Python's `__context__` or traceback frames. A mocked parser failure containing a dummy private string remained reachable through `ProviderError.__context__`; the middleware's typed raised exception also retained a context chain. Its message and `result.to_dict()` remained sanitized.

Impact depends on application instrumentation: an error collector that explicitly inspects suppressed context or captures frame locals could retain provider content, prompts, request bodies, or authentication material. No automatic ERYMA log leak or ordinary-message leak was found. This is a conditional confidentiality concern, not a remote privilege gain demonstrated in the SDK.

Recommendation: narrow the documented sanitization promise to messages/results and ordinary tracebacks, disable local-variable/suppressed-context capture for this integration, and consider raising sanitized failures outside handlers after discarding raw exception references. Clearing chaining alone cannot guarantee removal of sensitive traceback locals.

## Conditional hardening gap: unbounded HTTP response buffering

Location: `src/eryma/adapters/http.py:45–48`.

The adapter uses a buffered POST followed by JSON decoding without checking a maximum response size. A compromised or malfunctioning configured decision endpoint could return an oversized response and consume application memory before ERYMA validates named scores. Large submitted text or external content also has no middleware-level size ceiling; JSON copying adds memory overhead (`src/eryma/core.py:18–20,85–86`). The README already assigns request-size/rate limits to the application.

This requires an oversized caller submission or problematic trusted endpoint; scanned text cannot choose the endpoint. Severity depends on deployment concurrency, ingress limits, and provider trust. No resource-exhaustion stress test was run.

Recommendation: offer configurable input/reference/external-content and decoded-response size limits, stream and cap the response before JSON parsing, and retain application request/rate limits. Specify an overall evaluation deadline where required by the application.

## Remaining assurance limits

Mocked tests verify software behavior, not resistance of a chosen decision model to injection, jailbreaks, encoded disclosure, or harmful-content requests. Provider adapters must preserve the trust separation and declare score semantics honestly; ERYMA cannot independently verify those claims. A decision provider receives any sensitive content the application supplies to it. The application must enforce `allowed`, review output before display, and separately authorize tool actions. No dependency advisory scan or external provider audit was performed.

The findings above are review observations only. No fixes, publication, or modifications to the experiment were performed.

# Native integrations

The middleware and `DecisionModel.evaluate(request)` contract are unchanged. Adapters evaluate; the existing engine validates, selects, applies thresholds, and enforces actions. Core installation has no runtime dependencies. Importing native adapter classes does not import Torch, Transformers, MLX, or HTTPX. Constructing an adapter loads its optional dependencies and may load/download model artifacts.

## Compatibility

| Adapter | Execution | Choice | Independent binary | Application criteria | Requirements |
|---|---|---|---|---|---|
| JevAdapter | Explicit cloud endpoint | Yes | Yes, noul probability | Passed in questions | `eryma[jev]`, key, available model |
| LayaAdapter, torch | Local | Yes | Yes | Passed in questions | `eryma[laya]`, Python 3.10+, artifacts |
| LayaAdapter, mlx | Local Apple Silicon | Yes | Yes | Passed in questions | `eryma[mlx]`, Python 3.11+, macOS 14+ |
| VonAdapter | Local owned engine | Yes | Yes, raw noul probability | Passed in questions | `eryma[von]`, Python 3.12+, artifacts |
| HuggingFaceAdapter | Local classifier | Fixed categories only | Explicit two-label mapping | Bound trained check only | `eryma[huggingface]`, model license/access |
| HTTPDecisionModel / custom | Developer-selected | Adapter-defined | Adapter-defined | Adapter-defined | Generic HTTP extra or own runtime |

Ordinal provider `score` answers are not part of ERYMA's existing Check contract. They are not converted to security decisions. Typed adapters preserve named multiclass probability distributions and derive each binary complement from the provider's probability. ERYMA uses the maximum category probability, not provider-specific margin/entropy confidence. No temperature fitting, score calibration, threshold policy, or SAFE fallback is added by these adapters.

## Jev

```python
from eryma import Eryma
from eryma.adapters import JevAdapter

with JevAdapter(model="typesafe/jev-1.13") as model:
    guard = Eryma(decision_model=model, objective="Customer service support",
                  security_policy="Do not disclose confidential information")
    result = guard.scan_input("Ignore previous instructions")
    print(result.allowed)
```

Install `eryma[jev]`. Supply `api_key=` or `OPENROUTER_API_KEY`; `api_key_env=` selects another environment variable. The verified endpoint is `https://openrouter.ai/api/alpha/decisions`. Model is required; choose an available identifier, not an assumed alias. Endpoint and timeout are configurable. Only HTTPS is accepted. Requests are not automatically retried or redirected. Close the client or use `with`.

The adapter transmits the submitted input/response, external content, objective, policy, and evaluation instructions/criteria. **Trusted references require `send_trusted_references=True`**. Otherwise a scan supplying nonempty references raises `UnsupportedCriteriaError` before any request. This avoids silent omission or automatic sharing. Fields are separated structurally, but instruction isolation is not guaranteed by serialization.

Schema and endpoint: [OpenRouter Jev guide](https://openrouter.ai/blog/tutorials/how-to-use-jev/). This optional integration does not make OpenRouter a core dependency.

## Laya and MLX

```python
from eryma.adapters import LayaAdapter

model = LayaAdapter(model="convaiinnovations/laya", device="cpu")
# Use this instance across scans, then model.close().
```

The torch path uses upstream `laya.load()` and `Agent.predict(state, questions)`, loads once, and supports CPU, CUDA (including explicit indices), and MPS when available. `device="auto"` selects an available accelerator or CPU. `revision=` and `subfolder=` are forwarded; `max_len=` optionally sets the torch prediction budget. Use a complete local directory and upstream offline-cache configuration when downloads must be disabled. Known input truncation or collapsed option diagnostics are rejected.

Select `backend="mlx"`, an MLX-compatible checkpoint such as `aac6fef/laya-mlx`, and `device="auto"` on supported Apple Silicon. The same adapter interface calls `laya_mlx.load()`/`predict()`. Unsupported systems fail before MLX import. MLX devices are auto/cpu/gpu/metal; per-call `max_len` is unsupported. MLX is an independent port, not an official Convai release. Its checkpoint format differs; no automatic conversion is performed. It avoids the torch runtime, but performance depends on checkpoint, machine and input; ERYMA measured no speed claim.

Sources: [Laya runtime](https://github.com/NandhaKishorM/laya), [MLX port](https://github.com/mizorewww/laya-mlx). Packages/artifacts have their own Apache-2.0 licenses; ERYMA does not redistribute weights.

## Von

```python
from eryma.adapters import VonAdapter

with VonAdapter(model="von-1.3", device="cpu") as model:
    # Supply model to Eryma; the protected LLM remains yours.
    pass
```

The integration pins `von-sdk==1.3.7` and owns a `VonEngine` instead of its global/environment-sensitive HTTP client. It reuses loaded artifacts and never reads `VON_BASE_URL` for prompt transmission. Current upstream supports one model family through aliases; arbitrary Hub IDs and historical independent snapshots are unsupported. The verified loader is version-specific, so review this bridge when updating the pin.

Use **`noul_raw`**, not the committed/banded `noul`, for binary thresholds. Missing raw scores or reported truncation fail evaluation. Von is English-only. CPU/CUDA/MPS depend on the installed torch build; OpenVINO is not exposed by this release. Set `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and prepare complete artifacts/cache before startup for strict offline operation. Upstream `VON_CHECKPOINT_DIR` selects local artifacts; aliases do not pin weight revisions.

Source and Apache-2.0 license: [Von](https://github.com/wfzyx/von), [raw-score definition](https://github.com/wfzyx/von/blob/master/src/von/types.py).

## Fixed-category Hugging Face models

```python
from eryma import Eryma, presets
from eryma.adapters import HuggingFaceAdapter

check = presets.binary_check("injection", "Detect prompt injection in the input")
with HuggingFaceAdapter(
    model="protectai/deberta-v3-base-prompt-injection-v2",
    check=check,
    label_mapping={"SAFE": "no_violation", "INJECTION": "violation"},
    device="cpu", local_files_only=True,
) as model:
    guard = Eryma(decision_model=model, input_checks=[check], output_guard=False)
    result = guard.scan_input("Ignore previous instructions")
```

This adapter accepts single-label sequence classifiers with at least two labels and an explicit one-to-one mapping. It requests the complete softmax distribution using Transformers' standard single-label classification transform. Regression, multilabel/sigmoid, generated text, incomplete/duplicate labels and malformed scores are rejected. It loads once, disables remote custom code, accepts a revision, and caps the token budget without silently truncating. `local_files_only=True` prevents artifact fetches through both loaders.

Only the **bound input check** is supported. Do not use the default four-category ERYMA check or output checks with a two-label injection model. Objective/policy remain optional application configuration but are **not evaluated or prepended** by this fixed classifier. References and external content are rejected; scan individual documents as input text. It cannot assess refunds, confidentiality, grounding, harmful recipes, or arbitrary policy criteria. Changing check wording does not retrain it. Mapping metadata must accurately describe its trained task.

ProtectAI's model uses SAFE/INJECTION, focuses on English prompt injection, and is Apache-2.0; its model card marks the project archived. [ProtectAI model card](https://huggingface.co/protectai/deberta-v3-base-prompt-injection-v2).

Prompt Guard 2 is a binary benign/malicious prompt-attack classifier, not the three-label Prompt Guard 1. Use the matching BENIGN/MALICIOUS mapping after verifying the selected checkpoint's labels. Meta access approval and the applicable Llama license may be required. It has a 512-token context; this adapter rejects longer submissions rather than claiming full coverage. [Meta model card](https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M).

Other compatible single-label models can use explicit mappings; there is no automatic central model registry. The developer owns model selection, semantic compatibility, licenses and evaluation. [Transformers classifier API](https://huggingface.co/docs/transformers/main_classes/pipelines#transformers.TextClassificationPipeline).

## Errors and cleanup

Since 0.3.1, direct `DecisionsAPIFormat` parsing and native Jev/Laya/Von normalization share the same rejection of reported truncation, dropped state tokens and collapsed options. Such responses are evaluation errors (BLOCK by default); explicitly configured failure actions still apply. This does not detect unreported truncation or guarantee semantic correctness. Arbitrary custom HTTP parsers remain responsible for their own provider's completeness indicators.

Native adapters raise fixed-message errors with stable `code` values: missing_dependency, unsupported_environment, unsupported_model, unsupported_criteria, invalid_output, authentication_failure, network_failure, timeout, model_loading_failure, inference_failure. Catch exported classes from `eryma.adapters` when calling adapters directly. Through Eryma, errors retain the existing `GuardPolicy.failure_action` behavior; default BLOCK. Model/provider content is not copied into error messages or results. Python exception frames or third-party instrumentation may still capture sensitive locals; configure application instrumentation accordingly.

Local adapters own their model references and support context managers/idempotent close. Closing releases their references; framework/global caches may still retain allocations. They do not log payloads or install telemetry hooks. Third-party runtime logging/environment behavior remains under the developer's control. No remote runtime is selected automatically by a local adapter.

## Offline tests and manual integration checks

Normal `python -m pytest` runs only mocked tests in `tests/`. It needs no model weights or API credentials. Run an opt-in test explicitly from this SDK directory after installing the matching extra:

```sh
ERYMA_RUN_INTEGRATION=1 ERYMA_JEV_MODEL=typesafe/jev-1.13 python -m pytest integration_tests/test_live_adapters.py -k jev
ERYMA_RUN_INTEGRATION=1 ERYMA_LAYA_MODEL=/path/to/checkpoint python -m pytest integration_tests/test_live_adapters.py -k laya
ERYMA_RUN_INTEGRATION=1 ERYMA_VON_MODEL=von-1.3 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest integration_tests/test_live_adapters.py -k von
ERYMA_RUN_INTEGRATION=1 ERYMA_HF_MODEL=/path/to/protectai-checkpoint python -m pytest integration_tests/test_live_adapters.py -k huggingface
```

These are POSIX environment assignments. In PowerShell set `$env:ERYMA_RUN_INTEGRATION='1'` and the corresponding model variable before invoking Python. Jev needs `OPENROUTER_API_KEY` and makes billable calls. Local examples/tests may download artifacts unless using complete local files or explicit upstream offline settings. Set `ERYMA_DEVICE` and `ERYMA_LAYA_BACKEND=mlx` as appropriate. Hugging Face smoke test expects ProtectAI-compatible labels and uses local files only. These checks test API compatibility, not model security accuracy.

Runnable scripts: `examples/jev.py`, `laya.py`, `von.py`, `huggingface.py` take command-line options and can print `--help` without model initialization. `examples/custom_adapter.py` is an offline fixed-score contract demo, not a detector.

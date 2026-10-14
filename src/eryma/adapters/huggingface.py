"""Local, fixed-category single-label classifiers with explicit category bindings."""
from ..types import Check, ScoreDistribution, ScoreKind, finite_number
from ..decisions import validate_scores
from ._shared import optional_module, device_for_torch
from .errors import (UnsupportedModelError, UnsupportedCriteriaError, InvalidOutputError,
                     ModelLoadingError, InferenceError)


class HuggingFaceAdapter:
    def __init__(self, *, model: str, check: Check, label_mapping: dict[str, str],
                 device: str = "auto", revision: str | None = None,
                 local_files_only: bool = False, max_tokens: int = 512):
        if not isinstance(model, str) or not model.strip():
            raise UnsupportedModelError()
        if not isinstance(check, Check) or check.requires_objective or check.requires_references:
            raise UnsupportedCriteriaError()
        if not isinstance(label_mapping, dict) or (not all(isinstance(k, str) and isinstance(v, str)
                for k, v in label_mapping.items())
                or set(label_mapping.values()) != set(check.criteria)
                or len(label_mapping) != len(check.criteria)):
            raise UnsupportedCriteriaError()
        if type(local_files_only) is not bool or type(max_tokens) is not int or max_tokens <= 0:
            raise ValueError("Use a boolean local_files_only and positive max_tokens")
        self._check = Check(check.name, check.instructions, check.criteria, check.actions, check.kind)
        self._mapping = dict(label_mapping)
        self._closed = False
        selected_device = device_for_torch(device, "huggingface")
        transformers = optional_module("transformers", "huggingface")
        options = dict(local_files_only=local_files_only, trust_remote_code=False)
        if revision is not None:
            options["revision"] = revision
        try:
            self._tokenizer = transformers.AutoTokenizer.from_pretrained(model, **options)
            loaded = transformers.AutoModelForSequenceClassification.from_pretrained(model, **options)
        except Exception:
            raise ModelLoadingError() from None
        try:
            config = loaded.config
            labels = config.id2label
            supported = (isinstance(labels, dict)
                and getattr(config, "problem_type", None) in (None, "single_label_classification")
                and set(labels.values()) == set(self._mapping)
                and getattr(config, "num_labels", 0) == len(self._mapping))
        except Exception:
            supported = False
        if not supported:
            raise UnsupportedModelError()
        # Softmax is the standard single-label classifier transformation. No sigmoid,
        # raw-logit or generated-text result is silently treated as a distribution.
        try:
            self._pipeline = transformers.pipeline("text-classification", model=loaded,
                tokenizer=self._tokenizer, device=selected_device, framework="pt")
        except Exception:
            raise ModelLoadingError() from None
        limits = [max_tokens]
        for value in (getattr(self._tokenizer, "model_max_length", None),
                      getattr(config, "max_position_embeddings", None)):
            if isinstance(value, int) and 0 < value < 1_000_000:
                limits.append(value)
        self._max_tokens = min(limits)

    def evaluate(self, request):
        if self._closed:
            raise InferenceError()
        if request.guard != "input" or len(request.checks) != 1:
            raise UnsupportedCriteriaError()
        check = request.checks[0]
        bound = self._check
        if (check.name, check.instructions, dict(check.criteria), check.kind,
            check.requires_objective, check.requires_references) != (
                bound.name, bound.instructions, dict(bound.criteria), bound.kind, False, False):
            raise UnsupportedCriteriaError()
        if request.trusted_context.get("references") or request.untrusted_data.get("external_content") is not None:
            raise UnsupportedCriteriaError()
        text = request.untrusted_data["user_message"]
        try:
            tokens = self._tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"]
        except Exception:
            raise InferenceError() from None
        if len(tokens) > self._max_tokens:
            # No silent truncation that might remove an attack at the end of the input.
            raise UnsupportedCriteriaError()
        try:
            output = self._pipeline(text, top_k=None, function_to_apply="softmax", truncation=False)
        except Exception:
            raise InferenceError() from None
        try:
            if not isinstance(output, list) or len(output) != len(self._mapping):
                raise ValueError()
            scores = {}
            for item in output:
                label = item["label"]
                if label not in self._mapping or self._mapping[label] in scores:
                    raise ValueError()
                scores[self._mapping[label]] = finite_number(item["score"])
            values, kind = validate_scores(check, ScoreDistribution(scores, ScoreKind.PROBABILITY))
            return {check.name: ScoreDistribution(values, kind)}
        except Exception:
            raise InvalidOutputError() from None

    def close(self):
        self._pipeline, self._tokenizer = None, None
        self._closed = True

    def __enter__(self):
        if self._closed:
            raise InferenceError()
        return self

    def __exit__(self, *args):
        self.close()

"""Local VonEngine integration; never invokes its environment-sensitive HTTP client."""
import sys
from copy import deepcopy
from ._shared import TypedLocalAdapter, optional_module, device_for_torch, normalize
from .errors import (UnsupportedEnvironmentError, UnsupportedModelError,
                     ModelLoadingError, InferenceError, InvalidOutputError)


class VonAdapter(TypedLocalAdapter):
    def __init__(self, *, model: str = "von-1.3", device: str = "auto"):
        self._setup(model)
        if sys.version_info < (3, 12):
            raise UnsupportedEnvironmentError()
        selected_device = device_for_torch(device, "von")
        module = optional_module("von.engine", "von")
        if model.lower().strip() not in getattr(module, "SUPPORTED_BACKENDS", ()):
            raise UnsupportedModelError()
        try:
            # Own an instance rather than altering Von's process-global singleton.
            self._runtime = module.VonEngine(backend_name=model, device=selected_device)
            # Verified von-sdk 1.3.7 loader; pin this integration's SDK version.
            self._runtime.backend._get_model()
        except Exception:
            raise ModelLoadingError() from None

    def evaluate(self, request):
        if self._closed:
            raise InferenceError()
        payload = self._formatter.build_request(request)
        try:
            response = self._runtime.evaluate(state=payload["state"],
                questions=payload["questions"], model=payload["model"])
            data = response.model_dump(mode="json")
        except Exception:
            raise InferenceError() from None
        try:
            data = deepcopy(data)
            for check in request.checks:
                if check.kind == "binary":
                    answer = data["answers"][check.name]
                    # The committed `noul` band is not suitable for confidence gates.
                    if answer.get("noul_raw") is None:
                        raise ValueError()
                    answer["noul"] = answer["noul_raw"]
        except Exception:
            raise InvalidOutputError() from None
        return normalize(data, request, self._formatter)

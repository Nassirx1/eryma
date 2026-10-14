"""Laya torch and optional independent MLX-port integration."""
from ._shared import (TypedLocalAdapter, optional_module, device_for_torch,
                      require_mlx_environment, normalize)
from .errors import (UnsupportedEnvironmentError, UnsupportedModelError,
                     ModelLoadingError, InferenceError)


class LayaAdapter(TypedLocalAdapter):
    def __init__(self, *, model: str = "convaiinnovations/laya", device: str = "cpu",
                 backend: str = "torch", revision: str | None = None,
                 subfolder: str | None = None, max_len: int | None = None):
        self._setup(model)
        if backend not in ("torch", "mlx"):
            raise UnsupportedEnvironmentError()
        if max_len is not None and (type(max_len) is not int or max_len <= 0):
            raise ValueError("max_len must be a positive integer")
        self._backend, self._max_len = backend, max_len
        if backend == "mlx":
            require_mlx_environment()
            if device not in ("auto", "cpu", "gpu", "metal") or max_len is not None:
                raise UnsupportedEnvironmentError()
            module = optional_module("laya_mlx", "mlx")
            selected_device = None if device == "auto" else device
        else:
            selected_device = device_for_torch(device, "laya")
            module = optional_module("laya", "laya")
        loader = getattr(module, "load", None)
        if not callable(loader):
            raise UnsupportedModelError()
        try:
            self._runtime = loader(model, device=selected_device, revision=revision, subfolder=subfolder)
        except Exception:
            raise ModelLoadingError() from None
        if not callable(getattr(self._runtime, "predict", None)):
            self.close()
            raise UnsupportedModelError()

    def evaluate(self, request):
        if self._closed:
            raise InferenceError()
        payload = self._formatter.build_request(request)
        kwargs = {"max_len": self._max_len} if self._max_len is not None else {}
        try:
            data = self._runtime.predict(payload["state"], payload["questions"], **kwargs)
        except Exception:
            raise InferenceError() from None
        return normalize(data, request, self._formatter)

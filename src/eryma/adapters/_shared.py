"""Shared wire normalization and explicit optional-runtime loading."""
import importlib
import platform
import sys
from ..decisions import validate_scores
from ..types import ScoreDistribution
from .decisions_api import DecisionsAPIFormat
from .errors import (MissingDependencyError, UnsupportedEnvironmentError,
                     InvalidOutputError, UnsupportedModelError)


def optional_module(name, extra=None):
    try:
        return importlib.import_module(name)
    except ImportError:
        raise MissingDependencyError(extra) from None


def device_for_torch(device, extra=None):
    if not isinstance(device, str) or not device:
        raise UnsupportedEnvironmentError()
    torch = optional_module("torch", extra)
    if device == "auto":
        if torch.cuda.is_available():
            return "cuda"
        mps = getattr(getattr(torch, "backends", None), "mps", None)
        return "mps" if mps and mps.is_available() else "cpu"
    if device == "cpu":
        return device
    if device == "cuda" or device.startswith("cuda:"):
        if not torch.cuda.is_available():
            raise UnsupportedEnvironmentError()
        if ":" in device:
            try:
                index = int(device.split(":", 1)[1])
            except ValueError:
                raise UnsupportedEnvironmentError() from None
            if not 0 <= index < torch.cuda.device_count():
                raise UnsupportedEnvironmentError()
        return device
    if device == "mps":
        mps = getattr(getattr(torch, "backends", None), "mps", None)
        if mps and mps.is_available():
            return device
    raise UnsupportedEnvironmentError()


def require_mlx_environment():
    if (platform.system() != "Darwin" or platform.machine().lower() != "arm64"
            or sys.version_info < (3, 11)):
        raise UnsupportedEnvironmentError()
    try:
        major = int(platform.mac_ver()[0].split(".")[0])
    except ValueError:
        raise UnsupportedEnvironmentError() from None
    if major < 14:
        raise UnsupportedEnvironmentError()


def normalize(data, request, formatter):
    try:
        raw = formatter.parse_response(data, request)
        return {check.name: ScoreDistribution(*validate_scores(check, raw[check.name]))
                for check in request.checks}
    except Exception:
        raise InvalidOutputError() from None


class TypedLocalAdapter:
    """Shared local predict bridge; model libraries perform inference, not enforcement."""
    def _setup(self, model):
        if not isinstance(model, str) or not model.strip():
            raise UnsupportedModelError()
        self._formatter = DecisionsAPIFormat(model=model)
        self._runtime = None
        self._closed = False

    def close(self):
        if not self._closed:
            runtime, self._runtime = self._runtime, None
            self._closed = True
            # The Laya torch runtime documents its context-manager cleanup.
            cleanup = getattr(runtime, "__exit__", None)
            if callable(cleanup):
                try:
                    cleanup(None, None, None)
                except Exception:
                    from .errors import InferenceError
                    raise InferenceError() from None

    def __enter__(self):
        if self._closed:
            raise UnsupportedModelError()
        return self

    def __exit__(self, *args):
        self.close()

"""Lazy optional adapters; importing this module does not load model runtimes."""
from importlib import import_module
from .errors import (AdapterError, MissingDependencyError, UnsupportedEnvironmentError,
    UnsupportedModelError, UnsupportedCriteriaError, InvalidOutputError,
    AuthenticationError, NetworkError, AdapterTimeoutError, ModelLoadingError, InferenceError)

_ADAPTERS = {"JevAdapter": ".jev", "LayaAdapter": ".laya", "VonAdapter": ".von",
             "HuggingFaceAdapter": ".huggingface", "HTTPDecisionModel": ".http",
             "DecisionsAPIFormat": ".decisions_api"}


def __getattr__(name):
    if name not in _ADAPTERS:
        raise AttributeError(name)
    value = getattr(import_module(_ADAPTERS[name], __name__), name)
    globals()[name] = value
    return value


__all__ = list(_ADAPTERS) + ["AdapterError", "MissingDependencyError",
    "UnsupportedEnvironmentError", "UnsupportedModelError", "UnsupportedCriteriaError",
    "InvalidOutputError", "AuthenticationError", "NetworkError", "AdapterTimeoutError",
    "ModelLoadingError", "InferenceError"]

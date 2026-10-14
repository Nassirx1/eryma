"""Stable adapter failures; messages never include provider content."""


class AdapterError(RuntimeError):
    code = "adapter_error"
    message = "Decision adapter failed"

    def __init__(self):
        super().__init__(self.message)


class MissingDependencyError(AdapterError, ImportError):
    code = "missing_dependency"
    message = "Install the documented optional integration extra in this environment"

    def __init__(self, extra=None):
        if extra in ("http", "jev", "laya", "von", "mlx", "huggingface"):
            self.message = f"Install eryma[{extra}] in this Python environment"
        super().__init__()


class UnsupportedEnvironmentError(AdapterError):
    code = "unsupported_environment"
    message = "The selected backend, device, or Python version is unsupported"


class UnsupportedModelError(AdapterError):
    code = "unsupported_model"
    message = "The selected model or installed model-library interface is unsupported"


class UnsupportedCriteriaError(AdapterError):
    code = "unsupported_criteria"
    message = "This adapter cannot evaluate the supplied checks or context"


class InvalidOutputError(AdapterError):
    code = "invalid_output"
    message = "The decision model returned invalid or incomplete scores"


class AuthenticationError(AdapterError):
    code = "authentication_failure"
    message = "Decision-provider credentials are missing or authentication failed"


class NetworkError(AdapterError):
    code = "network_failure"
    message = "Decision-provider transport or API request failed"


class AdapterTimeoutError(NetworkError):
    code = "timeout"
    message = "Decision-provider request timed out; it has not been retried"


class ModelLoadingError(AdapterError):
    code = "model_loading_failure"
    message = "Local decision-model artifacts could not be loaded"


class InferenceError(AdapterError):
    code = "inference_failure"
    message = "Local decision-model inference failed"

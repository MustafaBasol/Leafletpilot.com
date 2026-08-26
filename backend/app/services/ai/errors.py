class AIError(Exception):
    code = "ai_error"

    def __init__(self, message: str, *, provider: str = "", model: str = "") -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model


class AIConfigurationError(AIError):
    code = "invalid_configuration"


class AIUnsupportedCapabilityError(AIError):
    code = "unsupported_capability"


class AIProviderError(AIError):
    code = "provider_error"


class AIProviderTransientError(AIProviderError):
    code = "provider_unavailable"


class AIProviderTimeoutError(AIProviderTransientError):
    code = "provider_timeout"


class AIProviderAuthenticationError(AIProviderError):
    code = "provider_authentication"


class AIProviderOutputError(AIProviderError):
    code = "schema_invalid"

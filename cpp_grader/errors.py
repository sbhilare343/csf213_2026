class GraderError(Exception):
    """Base exception for expected user-facing grader errors."""

class ConfigurationError(GraderError):
    pass

class InputValidationError(GraderError):
    pass

class SandboxUnavailableError(GraderError):
    pass

class InfrastructureError(GraderError):
    pass

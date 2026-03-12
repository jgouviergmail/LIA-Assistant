"""
Custom exceptions for agent tools.

Provides typed exceptions for better error handling and i18n support.
These exceptions are caught by tool wrappers to return appropriate
UnifiedToolOutput.failure() responses.

Created: 2025-01-12
"""


class ToolError(Exception):
    """Base exception for all tool errors."""

    pass


class ConnectorNotEnabledError(ToolError):
    """
    Connector not enabled for user.

    Raised when a draft execution requires a connector that is not activated.
    Uses i18n message from APIMessages.connector_not_enabled().

    Attributes:
        connector_name: Name of the missing connector (e.g., "Google Calendar")
    """

    def __init__(self, message: str, connector_name: str | None = None):
        self.connector_name = connector_name
        super().__init__(message)


class ToolValidationError(ToolError):
    """
    Generic tool input validation failed.

    Raised when required fields are missing or have invalid format.
    Can be used across all tool domains (calendar, contacts, tasks, drive, etc.).

    Attributes:
        field: Optional field name that failed validation
    """

    def __init__(self, message: str, field: str | None = None):
        self.field = field
        super().__init__(message)


class EmailToolError(ToolError):
    """Base exception for email tool errors."""

    pass


class EmailValidationError(EmailToolError):
    """
    Email input validation failed.

    Raised when required fields are missing or have invalid format.

    Attributes:
        field: Optional field name that failed validation
    """

    def __init__(self, message: str, field: str | None = None):
        self.field = field
        super().__init__(message)


class ContentGenerationError(EmailToolError):
    """
    LLM content generation failed.

    Raised when content_instruction processing fails
    (e.g., invalid JSON response, empty content).
    """

    pass


# =============================================================================
# LABEL TOOL EXCEPTIONS
# =============================================================================


class LabelToolError(ToolError):
    """Base exception for label tool errors."""

    pass


class LabelNotFoundError(LabelToolError):
    """
    Raised when label doesn't exist.

    Attributes:
        label_name: Name of the label that was not found
    """

    def __init__(self, message: str, label_name: str | None = None):
        self.label_name = label_name
        super().__init__(message)


class LabelAlreadyExistsError(LabelToolError):
    """
    Raised when trying to create duplicate label.

    Attributes:
        label_name: Name of the duplicate label
    """

    def __init__(self, message: str, label_name: str | None = None):
        self.label_name = label_name
        super().__init__(message)


class SystemLabelError(LabelToolError):
    """
    Raised when trying to modify system label.

    Attributes:
        label_name: Name of the system label
    """

    def __init__(self, message: str, label_name: str | None = None):
        self.label_name = label_name
        super().__init__(message)


class LabelAmbiguousError(LabelToolError):
    """
    Raised when label name matches multiple labels.

    Attributes:
        candidates: List of matching label candidates
    """

    def __init__(self, message: str, candidates: list[dict] | None = None):
        self.candidates = candidates or []
        super().__init__(message)

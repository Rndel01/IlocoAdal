"""Errors the UI can show to the user. Every message is safe to display as-is.

Each error has a stable `code` so the Flutter app can pick the right screen
without parsing the message text."""


class IlocoAdalError(Exception):
    """Base class for all expected, user-facing errors."""
    code = "error"


class UnsupportedFileError(IlocoAdalError):
    """UI screen: "This file can't be used" (wrong type, too large, protected)."""
    code = "unsupported_file"


class TextExtractionError(IlocoAdalError):
    """UI screen: "Can't read this document" (corrupted, scanned, no text)."""
    code = "cannot_read"


class NoKeyTermsError(IlocoAdalError):
    """UI screen: "No key terms found" (not enough text to rank)."""
    code = "no_key_terms"


class NoFilesError(IlocoAdalError):
    """Start Processing was pressed with no documents added."""
    code = "no_files"


class TermNotFoundError(IlocoAdalError):
    """A term typed into 'Add a term' does not occur in the document."""
    code = "term_not_found"


class CancelledError(IlocoAdalError):
    """The user cancelled the job."""
    code = "cancelled"


class ConfigError(IlocoAdalError):
    """The config file (or a per-job option) is invalid."""
    code = "config_error"


class ApiError(IlocoAdalError):
    """An online service (dictionary / translate) could not be used.
    ProcessManager catches these and continues without that service."""
    code = "api_error"


class ApiUnavailableError(ApiError):
    """No internet, timeout, server error, or missing API key."""
    code = "api_unavailable"


class ApiNotFoundError(ApiError):
    """The service answered, but has nothing for this request (HTTP 404)."""
    code = "api_not_found"

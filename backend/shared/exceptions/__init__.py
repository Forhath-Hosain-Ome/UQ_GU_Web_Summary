# Shared exceptions for the Puma Summary application

class PumaException(Exception):
    """Base exception for Puma-related errors."""
    pass

class InvalidPDFError(PumaException):
    """Raised when a PDF file is invalid or cannot be processed."""
    pass

class ExtractionError(PumaException):
    """Raised when data extraction from PDF fails."""
    pass

class FileProcessingError(PumaException):
    """Raised when file operations fail."""
    pass

class CertificateGenerationError(PumaException):
    """Raised when certificate generation fails."""
    pass
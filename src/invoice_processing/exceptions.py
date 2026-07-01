class InvoiceProcessingError(Exception):
    """Base exception for expected invoice processing failures."""


class ConfigurationError(InvoiceProcessingError):
    """Raised when runtime configuration is invalid."""


class UploadValidationError(InvoiceProcessingError):
    """Raised when an uploaded file is not acceptable for processing."""


class PdfSignatureError(UploadValidationError):
    """Raised when uploaded bytes do not have a PDF signature."""


class EmptyFileError(UploadValidationError):
    """Raised when an uploaded file is empty."""


class PdfReadError(InvoiceProcessingError):
    """Raised when a PDF cannot be read or inspected."""


class InvoiceParseError(InvoiceProcessingError):
    """Raised when an invoice does not match the supported parsing rules."""


class UnsupportedLayoutError(InvoiceParseError):
    """Raised when the PDF is readable but does not match supported invoice layout rules."""


class NoInvoiceRowsError(InvoiceParseError):
    """Raised when no invoice line-item rows are extracted."""


class ExportError(InvoiceProcessingError):
    """Raised when output cannot be written."""


class EmailDeliveryError(InvoiceProcessingError):
    """Raised when admin email delivery fails after sanitization."""


class UnexpectedProcessingError(InvoiceProcessingError):
    """Raised for unexpected per-file processing failures after they are captured safely."""

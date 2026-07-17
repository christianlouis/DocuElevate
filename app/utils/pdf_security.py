"""Safe handling for encrypted PDF inputs."""

from typing import BinaryIO

import pypdf
from pypdf import PasswordType
from pypdf.errors import FileNotDecryptedError

ENCRYPTED_PDF_ERROR_CODE = "encrypted_pdf_password_required"
ENCRYPTED_PDF_MESSAGE = (
    "This PDF is password-protected. Upload an unprotected copy, then start processing again. "
    "The original file was retained and was not sent to OCR or AI services."
)


class EncryptedPdfPasswordRequiredError(Exception):
    """Raised when a PDF cannot be opened without a user password."""


def open_pdf_reader(file_obj: BinaryIO) -> pypdf.PdfReader:
    """Open a PDF, accepting owner-password-only files with an empty user password."""
    reader = pypdf.PdfReader(file_obj)
    if not reader.is_encrypted:
        return reader

    try:
        password_type = reader.decrypt("")
    except FileNotDecryptedError as exc:
        raise EncryptedPdfPasswordRequiredError(ENCRYPTED_PDF_MESSAGE) from exc

    if password_type == PasswordType.NOT_DECRYPTED:
        raise EncryptedPdfPasswordRequiredError(ENCRYPTED_PDF_MESSAGE)
    return reader

"""Regression tests for bounded PDF page rendering in local OCR providers."""

from unittest.mock import Mock

import pytest


@pytest.mark.unit
def test_iter_pdf_pages_renders_and_closes_one_page_at_a_time():
    from app.utils.ocr_provider import _iter_pdf_pages

    pages = [Mock(name="page-1"), Mock(name="page-2")]
    calls = []

    def convert(_file_path, **kwargs):
        calls.append(kwargs)
        page_number = kwargs["first_page"]
        return [pages[page_number - 1]] if page_number <= len(pages) else []

    rendered = list(_iter_pdf_pages(convert, "/tmp/input.pdf", dpi=300))

    assert rendered == pages
    assert calls == [
        {"dpi": 300, "first_page": 1, "last_page": 1},
        {"dpi": 300, "first_page": 2, "last_page": 2},
        {"dpi": 300, "first_page": 3, "last_page": 3},
    ]
    for page in pages:
        page.close.assert_called_once_with()

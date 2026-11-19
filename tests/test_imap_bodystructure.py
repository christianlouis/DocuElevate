import pytest

from app.utils.imap_bodystructure import bodystructure_proves_no_named_attachment, metadata_uid_and_structure


@pytest.mark.unit
def test_text_bodystructure_proves_no_named_attachment():
    structure = b'("TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "7BIT" 12 1)'
    assert bodystructure_proves_no_named_attachment(structure)


@pytest.mark.unit
def test_named_and_unknown_structures_fall_back_to_full_fetch():
    assert not bodystructure_proves_no_named_attachment(
        b'("TEXT" "PLAIN" ("NAME" "invoice.pdf") NIL NIL "BASE64" 10 1)'
    )
    assert not bodystructure_proves_no_named_attachment(b'("TEXT" "PLAIN" ("NAME*0*" "invoice") NIL NIL "7BIT" 10 1)')
    assert not bodystructure_proves_no_named_attachment(b'("APPLICATION" "PDF" NIL NIL NIL "BASE64" 10)')
    assert not bodystructure_proves_no_named_attachment(b'("TEXT" "PLAIN"')


@pytest.mark.unit
def test_metadata_parser_handles_header_embedded_structure():
    uid, structure = metadata_uid_and_structure(
        (b'1 FETCH (UID 42 BODYSTRUCTURE ("TEXT" "HTML" NIL NIL NIL "7BIT" 4 1))', None)
    )
    assert uid == 42
    assert structure.startswith(b'("TEXT" "HTML"')


@pytest.mark.unit
def test_metadata_parser_handles_normal_imap_bytes_entry():
    uid, structure = metadata_uid_and_structure(
        b'99 FETCH (UID 99 BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 4 1))'
    )
    assert uid == 99
    assert bodystructure_proves_no_named_attachment(structure)

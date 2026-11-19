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
@pytest.mark.parametrize(
    "structure",
    [
        b'("TEXT" "PLAIN" NIL NIL NIL "7BIT" 4 1) trailing',
        b'("TEXT" "PLAIN" NIL NIL NIL "7BIT" 4 1 NIL ("INLINE" NIL))',
        b'("TEXT" "PLAIN" ("NAME*0*" "invoice") NIL NIL "7BIT" 4 1)',
        b'("TEXT" "PLAIN" NIL NIL NIL "7BIT" 4 1 ("x" "y")',
        b"(" * 33 + b'"TEXT" "PLAIN" NIL NIL NIL "7BIT" 4 1' + b")" * 33,
        b'("TEXT" "PLAIN" NIL NIL NIL "7BIT" 4 1)' + b" " * (64 * 1024),
    ],
)
def test_ambiguous_or_out_of_bounds_structures_fall_back_to_full_fetch(structure):
    assert not bodystructure_proves_no_named_attachment(structure)


@pytest.mark.unit
def test_metadata_parser_rejects_tuple_framing():
    uid, structure = metadata_uid_and_structure(
        (b'1 FETCH (UID 42 BODYSTRUCTURE ("TEXT" "HTML" NIL NIL NIL "7BIT" 4 1))', None)
    )
    assert uid is None
    assert structure is None


@pytest.mark.unit
@pytest.mark.parametrize("prefix", [b"99 ", b"99 FETCH ", b"* 99 FETCH "])
def test_metadata_parser_handles_normal_imap_bytes_entry(prefix):
    uid, structure = metadata_uid_and_structure(
        prefix + b'(UID 99 BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 4 1))'
    )
    assert uid == 99
    assert bodystructure_proves_no_named_attachment(structure)


@pytest.mark.unit
def test_tuple_literal_body_is_not_treated_as_bodystructure():
    uid, structure = metadata_uid_and_structure(
        (b"99 FETCH (UID 99 BODY[] {12})", b'("TEXT" "PLAIN" NIL NIL NIL "7BIT" 4 1)')
    )
    assert uid is None
    assert structure is None


@pytest.mark.unit
def test_trailing_tokens_and_quoted_parentheses_fail_closed():
    assert not bodystructure_proves_no_named_attachment(b'("TEXT" "PLAIN" ("CHARSET" "x (y)") NIL NIL "7BIT" 4 1) junk')


@pytest.mark.unit
def test_metadata_parser_handles_quoted_parentheses_without_losing_framing():
    uid, structure = metadata_uid_and_structure(
        b'1 FETCH (UID 1 BODYSTRUCTURE ("TEXT" "PLAIN" ("CHARSET" "x ) y") NIL NIL "7BIT" 4 1))'
    )
    assert uid == 1
    assert structure is not None
    assert bodystructure_proves_no_named_attachment(structure)


@pytest.mark.unit
@pytest.mark.parametrize(
    "item",
    [
        b'UID 4 BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 4 1)',
        b'4 FETCH (UID 4 BODYSTRUCTURE junk ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 4 1))',
        b'4 FETCH (UID 4 BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 4 1)) trailing',
        b'4 FETCH (UID 4 BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 4 1)',
        b'4 FETCH (UID 4 BODYSTRUCTURE ("TEXT" "PLAIN" NIL NIL NIL "7BIT" 4 1))' + b" " * (64 * 1024),
    ],
)
def test_metadata_parser_rejects_malformed_or_unbounded_raw_entries(item):
    assert metadata_uid_and_structure(item) == (None, None)

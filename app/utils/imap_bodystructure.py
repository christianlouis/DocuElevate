"""Conservative BODYSTRUCTURE classification for bounded IMAP scans."""

from __future__ import annotations

import re
from collections.abc import Iterator

_MAX_BYTES = 64 * 1024
_MAX_DEPTH = 32
_MAX_TOKENS = 20_000
_METADATA_PREFIX = re.compile(
    rb"^\s*(?:\*\s+)?\d+\s+FETCH\s+\(\s*UID\s+(\d+)\s+BODYSTRUCTURE\s+", re.IGNORECASE
)


class _ParseError(ValueError):
    pass


def _tokens(value: str) -> Iterator[object]:
    index = 0
    token_count = 0
    while index < len(value):
        token_count += 1
        if token_count > _MAX_TOKENS:
            raise _ParseError("too many tokens")
        if value[index].isspace():
            index += 1
        elif value[index] in "()":
            yield value[index]
            index += 1
        elif value[index] == '"':
            index += 1
            chars: list[str] = []
            while index < len(value):
                char = value[index]
                index += 1
                if char == "\\":
                    if index >= len(value):
                        raise _ParseError("unterminated escape")
                    chars.append(value[index])
                    index += 1
                elif char == '"':
                    yield ("string", "".join(chars))
                    break
                else:
                    chars.append(char)
            else:
                raise _ParseError("unterminated string")
        elif value[index] == "{":
            raise _ParseError("literal bodystructure unsupported")
        else:
            end = index
            while end < len(value) and not value[end].isspace() and value[end] not in "()":
                end += 1
            yield ("atom", value[index:end])
            index = end


def _parse(tokens: Iterator[object]) -> list[object]:
    if next(tokens, None) != "(":
        raise _ParseError("structure must start with list")

    def parse_list(depth: int = 1) -> list[object]:
        if depth > _MAX_DEPTH:
            raise _ParseError("structure too deep")
        result: list[object] = []
        for token in tokens:
            if token == ")":
                return result
            if token == "(":
                result.append(parse_list(depth + 1))
            else:
                result.append(token)
        raise _ParseError("unbalanced list")

    result = parse_list()
    if next(tokens, None) is not None:
        raise _ParseError("trailing structure data")
    return result


def _text_value(value: object) -> str | None:
    if (
        isinstance(value, tuple)
        and len(value) == 2
        and value[0] == "string"
        and isinstance(value[1], str)
    ):
        return value[1]
    return None


def _atom_value(value: object) -> str | None:
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "atom" and isinstance(value[1], str):
        return value[1]
    return None


def _nil(value: object) -> bool:
    atom = _atom_value(value)
    return atom is not None and atom.upper() == "NIL"


def _integer(value: object) -> bool:
    atom = _atom_value(value)
    return atom is not None and atom.isdigit()


def _safe_parameters(value: object) -> bool:
    """Accept only complete, nameless content-type parameter lists."""
    if _nil(value):
        return True
    if not isinstance(value, list) or len(value) % 2:
        return False
    for key, item in zip(value[::2], value[1::2], strict=False):
        key_text = _text_value(key)
        item_text = _text_value(item)
        if key_text is None or item_text is None:
            return False
        if re.search(r"(?:^|[-_])(name|filename)(?:\*\d*\*?|$)", key_text, re.IGNORECASE):
            return False
    return True


def _text_only(node: object) -> bool:
    """Prove a single complete body is plain/html text without extensions."""
    if not isinstance(node, list) or len(node) < 8:
        return False
    media_type = _text_value(node[0])
    subtype = _text_value(node[1])
    if media_type is None or subtype is None:
        return False
    if media_type.lower() != "text" or subtype.lower() not in {"plain", "html"}:
        return False
    if not _safe_parameters(node[2]) or not _nil(node[3]) or not _nil(node[4]):
        return False
    encoding = _text_value(node[5])
    if encoding is None or encoding.lower() not in {"7bit", "8bit", "binary", "base64", "quoted-printable"}:
        return False
    if not _integer(node[6]) or not _integer(node[7]):
        return False
    # BODY extensions have position-specific grammar.  Treat every non-NIL
    # extension (including disposition/language/location) as unknown.
    return all(_nil(value) for value in node[8:])


def bodystructure_proves_no_named_attachment(value: bytes | str) -> bool:
    """Return true only for a bounded, complete, nameless text body."""
    try:
        if isinstance(value, bytes):
            if len(value) > _MAX_BYTES:
                return False
            text = value.decode("ascii")
        else:
            if len(value.encode("ascii")) > _MAX_BYTES:
                return False
            text = value
        return _text_only(_parse(_tokens(text)))
    except (UnicodeDecodeError, UnicodeEncodeError, _ParseError):
        return False


def metadata_uid_and_structure(item: object) -> tuple[int | None, bytes | None]:
    """Extract a bounded ``UID BODYSTRUCTURE`` raw FETCH response only.

    imaplib can return tuples for literal payloads. Those have different
    framing and are deliberately not interpreted as metadata.
    """
    if not isinstance(item, bytes) or len(item) > _MAX_BYTES:
        return None, None
    match = _METADATA_PREFIX.match(item)
    if match is None:
        return None, None
    uid = int(match.group(1))
    if uid <= 0 or match.end() >= len(item) or item[match.end()] != ord("("):
        return None, None
    start = match.end()
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(item)):
        char = item[index]
        if quoted and escaped:
            escaped = False
        elif quoted and char == ord("\\"):
            escaped = True
        elif char == ord('"'):
            quoted = not quoted
        elif not quoted and char == ord("("):
            depth += 1
        elif not quoted and char == ord(")"):
            depth -= 1
            if depth == 0:
                if item[index + 1 :].strip() != b")":
                    return None, None
                return uid, item[start : index + 1]
    return None, None

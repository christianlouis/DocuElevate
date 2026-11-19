"""Conservative BODYSTRUCTURE classification for bounded IMAP scans."""

from __future__ import annotations

import re

_MAX_BYTES = 64 * 1024
_MAX_DEPTH = 32
_MAX_TOKENS = 20_000


class _ParseError(ValueError):
    pass


def _tokens(value: str):
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
            chars = []
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


def _parse(tokens):
    if next(tokens, None) != "(":
        raise _ParseError("structure must start with list")

    def parse_list(depth=1):
        if depth > _MAX_DEPTH:
            raise _ParseError("structure too deep")
        result = []
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


def _string(value):
    return isinstance(value, tuple) and value[0] == "string"


def _nil(value):
    return isinstance(value, tuple) and value[0] == "atom" and value[1].upper() == "NIL"


def _integer(value):
    return isinstance(value, tuple) and value[0] == "atom" and value[1].isdigit()


def _safe_parameters(value):
    if _nil(value):
        return True
    if not isinstance(value, list) or len(value) % 2:
        return False
    for key, item in zip(value[::2], value[1::2], strict=False):
        if not (_string(key) and _string(item)):
            return False
        if re.search(r"(?:^|[-_])(name|filename)(?:\*\d*\*?|$)", key[1], re.IGNORECASE):
            return False
    return True


def _safe_extension(value):
    return _nil(value) or _safe_parameters(value)


def _text_only(node):
    if not isinstance(node, list) or not node:
        return False
    if isinstance(node[0], list):
        children = []
        while node and isinstance(node[0], list):
            children.append(node.pop(0))
        if not children or not node or not _string(node[0]):
            return False
        return all(_text_only(child) for child in children) and all(_safe_extension(item) for item in node[1:])

    if len(node) < 8 or not (_string(node[0]) and _string(node[1])):
        return False
    if node[0][1].lower() != "text" or node[1][1].lower() not in {"plain", "html"}:
        return False
    if not _safe_parameters(node[2]) or not _nil(node[3]) or not _nil(node[4]):
        return False
    if not (_string(node[5]) and node[5][1].lower() in {"7bit", "8bit", "binary", "base64", "quoted-printable"}):
        return False
    if not _integer(node[6]) or not _integer(node[7]):
        return False
    return all(_safe_extension(item) for item in node[8:])


def bodystructure_proves_no_named_attachment(value: bytes | str) -> bool:
    """Return true only for a complete, known text-only structure."""
    try:
        if isinstance(value, bytes) and len(value) > _MAX_BYTES:
            return False
        text = value.decode("ascii") if isinstance(value, bytes) else value
        if len(text.encode("ascii", errors="ignore")) > _MAX_BYTES:
            return False
        return _text_only(_parse(iter(_tokens(text))))
    except (UnicodeDecodeError, _ParseError, TypeError):
        return False


def metadata_uid_and_structure(item) -> tuple[int | None, bytes | None]:
    """Extract UID and BODYSTRUCTURE from imaplib FETCH item bytes/tuples."""
    header = item[0] if isinstance(item, tuple) and item else item
    if not isinstance(header, (bytes, bytearray)):
        return None, None
    header = bytes(header)
    match = re.search(rb"\bUID\s+(\d+)\b", header, re.IGNORECASE)
    if not match or len(re.findall(rb"\bUID\s+\d+\b", header, re.IGNORECASE)) != 1:
        return None, None
    markers = list(re.finditer(rb"\bBODYSTRUCTURE\s+", header, re.IGNORECASE))
    if len(markers) != 1:
        return None, None
    marker = markers[0]
    if marker:
        start = header.find(b"(", marker.end())
        if start >= 0:
            depth = 0
            quoted = False
            escaped = False
            for index in range(start, len(header)):
                char = header[index]
                if quoted and escaped:
                    escaped = False
                elif quoted and char == 92:
                    escaped = True
                elif char == 34:
                    quoted = not quoted
                elif not quoted and char == 40:
                    depth += 1
                elif not quoted and char == 41:
                    depth -= 1
                    if depth == 0:
                        if header[index + 1 :].strip() != b")":
                            return None, None
                        return int(match.group(1)), header[start : index + 1]
    return None, None

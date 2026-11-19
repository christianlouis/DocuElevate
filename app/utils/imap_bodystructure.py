"""Conservative BODYSTRUCTURE classification for bounded IMAP scans."""

from __future__ import annotations

import re


class _ParseError(ValueError):
    pass


def _tokens(value: str):
    index = 0
    while index < len(value):
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

    def parse_list():
        result = []
        for token in tokens:
            if token == ")":
                return result
            if token == "(":
                result.append(parse_list())
            else:
                result.append(token)
        raise _ParseError("unbalanced list")

    return parse_list()


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

    if len(node) < 7 or not (_string(node[0]) and _string(node[1])):
        return False
    if node[0][1].lower() != "text" or node[1][1].lower() not in {"plain", "html"}:
        return False
    if not _safe_parameters(node[2]) or not _nil(node[3]) or not _nil(node[4]):
        return False
    if not (_string(node[5]) and node[5][1].lower() in {"7bit", "8bit", "binary", "base64", "quoted-printable"}):
        return False
    if not _integer(node[6]) or (len(node) >= 8 and not _integer(node[7])):
        return False
    return all(_safe_extension(item) for item in node[8:])


def bodystructure_proves_no_named_attachment(value: bytes | str) -> bool:
    """Return true only for a complete, known text-only structure."""
    try:
        text = value.decode("ascii") if isinstance(value, bytes) else value
        return _text_only(_parse(iter(_tokens(text))))
    except (UnicodeDecodeError, _ParseError, TypeError):
        return False


def metadata_uid_and_structure(item) -> tuple[int | None, bytes | None]:
    """Extract UID and BODYSTRUCTURE from imaplib FETCH item bytes/tuples."""
    header = item[0] if isinstance(item, tuple) and item else item
    body = item[1] if isinstance(item, tuple) and len(item) > 1 else None
    if not isinstance(header, (bytes, bytearray)):
        return None, None
    header = bytes(header)
    match = re.search(rb"\bUID\s+(\d+)\b", header, re.IGNORECASE)
    marker = re.search(rb"\bBODYSTRUCTURE\s+", header, re.IGNORECASE)
    if not match:
        return None, None
    if marker:
        start = header.find(b"(", marker.end())
        if start >= 0:
            depth = 0
            for index in range(start, len(header)):
                if header[index] == 40:
                    depth += 1
                elif header[index] == 41:
                    depth -= 1
                    if depth == 0:
                        return int(match.group(1)), header[start : index + 1]
    if isinstance(body, (bytes, bytearray)) and body.startswith(b"("):
        return int(match.group(1)), bytes(body)
    return None, None

import hashlib
from pathlib import Path


def hash_file(filepath: str | Path, chunk_size: int = 65536) -> str:
    """
    Returns the SHA-256 hash of the file at 'filepath'.
    Reads the file in chunks to handle large files efficiently.
    """
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            sha256.update(data)
    return sha256.hexdigest()

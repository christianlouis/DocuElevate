import hashlib
from pathlib import Path


def hash_file(filepath: str | Path, chunk_size: int = 65536) -> str:
    """
    Returns the SHA-256 hash of the file at 'filepath'.
    Reads the file in chunks to handle large files efficiently.
    """
    from app.config import settings

    filepath_obj = Path(filepath).resolve()
    workdir_obj = Path(settings.workdir).resolve()

    # Security check: Ensure the resolved path is strictly within the allowed workdir
    try:
        filepath_obj.relative_to(workdir_obj)
    except ValueError:
        raise FileNotFoundError(f"Access denied: path traversal attempt or file outside workdir '{filepath}'")

    sha256 = hashlib.sha256()
    with open(filepath_obj, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            sha256.update(data)
    return sha256.hexdigest()

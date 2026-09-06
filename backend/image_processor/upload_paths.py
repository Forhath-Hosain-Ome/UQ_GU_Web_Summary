"""Path rules for the Image Processor's private upload staging directory."""
from pathlib import Path, PureWindowsPath

from rest_framework.exceptions import ValidationError


def validate_upload_path(value: str, *, single_component: bool = False) -> str:
    """Reject unsafe components before normalization can hide traversal.

    Apply Windows rules on every host so uploads have the same interpretation
    on Windows and Linux. Folder labels otherwise retain their original text.
    """
    value = value.replace("\\", "/")
    parts = value.split("/")
    if (
        not value
        or PureWindowsPath(value).drive
        or value.startswith("/")
        or (single_component and len(parts) != 1)
        or any(
            part in ("", ".", "..")
            or part.endswith((".", " "))
            or len(part.encode("utf-8")) > 255
            or PureWindowsPath(part).is_reserved()
            or any(ord(c) < 32 or c in '<>:"|?*' for c in part)
            for part in parts
        )
    ):
        raise ValidationError("Invalid upload path.")
    return value


def contained_upload_path(root: Path, relative_path: str) -> Path:
    """Resolve containment and reject links, including Windows junctions.

    Call again after creating parents, immediately before exclusive file open.
    The job root is freshly created with owner-only access; no client selects it.
    """
    relative_path = validate_upload_path(relative_path)
    candidate = root
    for part in (None, *relative_path.split("/")):
        if part is not None:
            candidate = candidate / part
        if candidate.is_symlink() or candidate.is_junction():
            raise ValidationError("Upload paths must not contain links.")
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
    except (ValueError, OSError, RuntimeError) as exc:
        raise ValidationError("Invalid upload destination.") from exc
    return resolved


def validate_upload_destinations(paths: list[str]) -> None:
    """Reject overwrite and file/directory conflicts, also on case-folding hosts."""
    files = set()
    directories = set()
    directory_names = {}
    for path in paths:
        path = validate_upload_path(path)
        key = path.casefold()
        parts = key.split("/")
        parents = {"/".join(parts[:i]) for i in range(1, len(parts))}
        if key in files or key in directories or parents & files:
            raise ValidationError("Upload filenames collide after normalization.")
        files.add(key)
        directories.update(parents)
        original_parts = path.split("/")
        for i in range(1, len(original_parts)):
            name = "/".join(original_parts[:i])
            previous = directory_names.setdefault(name.casefold(), name)
            if previous != name:
                raise ValidationError("Upload folder names collide across platforms.")

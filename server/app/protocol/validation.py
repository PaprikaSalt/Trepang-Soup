from collections.abc import Iterable, Mapping
from typing import Any

PRIVATE_VALIDATION_FIELDS = {"ctx", "input", "url"}


def public_validation_errors(
    errors: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Remove submitted values and internal exception context from public errors."""

    return [
        {key: value for key, value in error.items() if key not in PRIVATE_VALIDATION_FIELDS}
        for error in errors
    ]

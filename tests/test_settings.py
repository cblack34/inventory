"""`Settings.db` must be an absolute path; `:memory:` is not a valid `DB`."""

import pytest
from pydantic import SecretStr, ValidationError

from inventory.settings import Settings

_VALID_KWARGS = {
    "SHARED_PASSWORD": SecretStr("correct horse"),
    "SESSION_SECRET": SecretStr("0" * 32),
    "TIMEZONE": "UTC",
    "INSECURE_COOKIES": True,
}


def test_memory_db_is_rejected_naming_db() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(DB=":memory:", **_VALID_KWARGS)

    assert "DB" in str(exc_info.value)


def test_relative_db_is_rejected_naming_db() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(DB="inventory.db", **_VALID_KWARGS)

    assert "DB" in str(exc_info.value)


def test_absolute_path_timezone_is_rejected_naming_timezone() -> None:
    """`ZoneInfo` raises plain `ValueError` for an absolute path, not `ZoneInfoNotFoundError`."""
    kwargs = {**_VALID_KWARGS, "TIMEZONE": "/etc/localtime"}
    with pytest.raises(ValidationError) as exc_info:
        Settings(DB="/tmp/inventory.db", **kwargs)

    assert "TIMEZONE" in str(exc_info.value)

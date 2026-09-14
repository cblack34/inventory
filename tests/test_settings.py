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

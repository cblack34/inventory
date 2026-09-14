"""`Settings.db` must be an absolute path; `:memory:` is not a valid `DB`."""

import pytest
from pydantic import SecretStr, ValidationError

from inventory.settings import MAX_PASSWORD_LENGTH, Settings, SettingsError, load_settings

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


def test_overlong_shared_password_is_rejected_naming_it() -> None:
    kwargs = {**_VALID_KWARGS, "SHARED_PASSWORD": SecretStr("x" * (MAX_PASSWORD_LENGTH + 1))}
    with pytest.raises(ValidationError) as exc_info:
        Settings(DB="/tmp/inventory.db", **kwargs)

    assert "SHARED_PASSWORD" in str(exc_info.value)


def test_overlong_shared_password_is_rejected_by_load_settings_naming_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`load_settings` reads from the environment, unlike the `Settings(...)` tests above."""
    monkeypatch.setenv("DB", "/tmp/inventory.db")
    monkeypatch.setenv("SHARED_PASSWORD", "x" * (MAX_PASSWORD_LENGTH + 1))
    monkeypatch.setenv("SESSION_SECRET", "0" * 32)
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.setenv("INSECURE_COOKIES", "true")

    with pytest.raises(SettingsError) as exc_info:
        load_settings()

    assert "SHARED_PASSWORD" in str(exc_info.value)

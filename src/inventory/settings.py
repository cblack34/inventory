"""Typed, fail-fast environment settings.

`Settings` declares every environment variable the app needs with no
default except `INSECURE_COOKIES` -- Compose supplies the rest, and a
missing or invalid value must fail startup rather than fall back to
something that quietly works on a developer's laptop and not in
production. `load_settings` turns pydantic's `ValidationError` into a
message that names the offending variable, for `__main__` to print to
stderr.
"""

from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MIN_SESSION_SECRET_BYTES = 32


class SettingsError(Exception):
    """Raised by `load_settings` when the environment is missing or invalid.

    The message names every offending environment variable so the
    container entrypoint can print it to stderr and exit non-zero.
    """


class Settings(BaseSettings):
    """The app's typed environment contract.

    No field below has a default except `insecure_cookies`; Compose
    supplies every other value, and this class never reads a `.env`
    file itself (`model_config` sets no `env_file`).
    """

    model_config = SettingsConfigDict(case_sensitive=False)

    db: str = Field(alias="DB")
    shared_password: SecretStr = Field(alias="SHARED_PASSWORD")
    session_secret: SecretStr = Field(alias="SESSION_SECRET")
    timezone: str = Field(alias="TIMEZONE")
    insecure_cookies: bool = Field(default=False, alias="INSECURE_COOKIES")

    @field_validator("db")
    @classmethod
    def _db_is_absolute_path(cls, value: str) -> str:
        """Reject `:memory:` along with any relative path.

        A relative path resolves against the process's current working
        directory, which is not guaranteed the same across the
        container entrypoint, `alembic`, and a developer's shell; an
        absolute path removes the ambiguity. `:memory:` is SQLite's own
        in-process database -- fine for a unit test that constructs an
        engine directly, but never a valid choice for this app's actual
        environment, since a real deployment always persists to disk.
        """
        if not Path(value).is_absolute():
            raise ValueError("DB must be an absolute path")
        return value

    @field_validator("shared_password")
    @classmethod
    def _password_non_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("SHARED_PASSWORD must not be empty")
        return value

    @field_validator("session_secret")
    @classmethod
    def _secret_at_least_32_bytes(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode("utf-8")) < _MIN_SESSION_SECRET_BYTES:
            raise ValueError("SESSION_SECRET must be at least 32 bytes when UTF-8 encoded")
        return value

    @field_validator("timezone")
    @classmethod
    def _timezone_is_known(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"TIMEZONE {value!r} is not a known IANA timezone name") from exc
        return value

    def __init__(self, **data: Any) -> None:
        """Re-declared only so pyright type-checks calls against this permissive signature.

        Without an explicit `__init__` here, pyright's `dataclass_transform`
        support synthesizes one from this class's own fields and treats
        every field lacking a Python-level default as a required
        constructor argument -- which breaks the zero-argument
        `Settings()` call `load_settings` relies on to read from the
        environment. This delegates straight to `BaseSettings.__init__`;
        runtime behavior is unchanged.
        """
        super().__init__(**data)


def load_settings() -> Settings:
    """Build `Settings` from the environment, raising `SettingsError` naming the bad variable(s)."""
    try:
        return Settings()
    except ValidationError as exc:
        offenders = "\n".join(f"{error['loc'][0]}: {error['msg']}" for error in exc.errors())
        raise SettingsError(f"invalid environment configuration:\n{offenders}") from exc

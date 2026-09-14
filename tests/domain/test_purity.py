"""Enforce that the domain package never imports FastAPI or SQLAlchemy.

Runs the check in a fresh subprocess, walking and importing every
submodule under ``inventory.domain`` via ``pkgutil.walk_packages`` (not
just the package ``__init__``, which alone wouldn't catch a submodule's
own framework import). Uses ``raise SystemExit``, not ``assert``, so the
check survives ``python -O``. A fresh subprocess also means another test
that already imported FastAPI or SQLAlchemy first can't taint this
process's ``sys.modules`` and produce a false failure.
"""

import subprocess
import sys
import textwrap

_SCRIPT = textwrap.dedent(
    """
    import importlib
    import pkgutil
    import sys

    import inventory.domain as domain_pkg

    for module_info in pkgutil.walk_packages(
        domain_pkg.__path__, domain_pkg.__name__ + "."
    ):
        importlib.import_module(module_info.name)

    if "fastapi" in sys.modules or "sqlalchemy" in sys.modules:
        raise SystemExit(1)
    raise SystemExit(0)
    """
)


def test_domain_package_imports_no_framework() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

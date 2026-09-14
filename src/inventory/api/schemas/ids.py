"""One shared id type for every id field and path parameter across the API.

`Id` is for a body field (a recipe line's `ingredient_id`, a movement's
`from_location_id`, and so on): `strict=True` rejects `"1"` or `1.5` for
an id the same way every other strict input model in
`inventory.api.schemas` does, and `ge=1, le=2**63 - 1` bounds it to a
positive value that fits SQLite's signed 64-bit `INTEGER PRIMARY KEY`
(see `inventory.db.models`), so `0`, a negative id, or an out-of-range
id becomes a 422 with an `errors` list rather than a 404 (no such row)
or a 500 (an out-of-range value the database driver cannot represent).
`IdPath` is the same bound for a route's `{..._id}` path parameter;
FastAPI validates a path parameter through `Path(...)`, not a Pydantic
field, so it needs its own annotation even though the bound is
identical.
"""

from typing import Annotated

from fastapi import Path
from pydantic import Field

_MAX_ID = 2**63 - 1

Id = Annotated[int, Field(strict=True, ge=1, le=_MAX_ID)]
IdPath = Annotated[int, Path(ge=1, le=_MAX_ID)]

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ImportRowDecision(BaseModel):
    """An explicit admin resolution for one preview row.

    ``target_id`` is contextual: for ``adopt_global`` it selects one global
    product among an ambiguous candidate set; for ``update_existing`` it may
    redirect to a different market product than preview detected.
    """

    action: Literal["adopt_global", "create_local", "update_existing", "skip"]
    target_id: UUID | None = None


class MarketCatalogImportCommitRequest(BaseModel):
    decisions: dict[str, ImportRowDecision] = Field(default_factory=dict)

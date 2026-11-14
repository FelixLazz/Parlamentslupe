"""Die Quelle vollständig erhalten, aber zentrale Identitätsfelder validieren."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class Entity(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: StrictInt = Field(gt=0)
    label: str
    entity_type: str | None = None


def validate_entity(payload: dict[str, Any]) -> dict[str, Any]:
    Entity.model_validate(payload)
    # Nicht model_dump verwenden: fehlende Felder und Originalwerte erhalten.
    return payload

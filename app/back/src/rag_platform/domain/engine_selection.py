"""Read-model de selección de motor de embedding por proyecto (plan §2.3.2).

Un ``ProjectEmbeddingEngine`` describe, para un proyecto, un motor de embedding
con artefactos **realmente materializados** (materialización sellada). Es un DTO
de solo lectura: agrupa por ``configuration_fingerprint`` la config semántica del
espacio vectorial (provider/model/revisión/dimensión/normalización/métrica) y
expone conteos auditables. No forma parte de la identidad de ningún artefacto ni
muta nada; acompaña a la matriz de variantes como filtro ``(project_id, motor)``
(decisión 2026-08-14).
"""

from __future__ import annotations

from pydantic import Field

from ingestion.schemas.common import StrictModel
from rag_platform.domain.models import PhysicalDistanceMetric


class ProjectEmbeddingEngine(StrictModel):
    """Motor de embedding con artefactos materializados dentro de un proyecto.

    Cada instancia agrupa los ``embedding_bundles`` de un proyecto que comparten
    ``configuration_fingerprint`` y que tienen al menos una materialización
    sellada en algún target. Los conteos permiten distinguir cobertura sin
    revelar contenido documental; ``configuration_fingerprint`` es el mismo
    digest que fija la config del motor en la receta semántica (ADR-006 §2.3).
    """

    configuration_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_revision: str = Field(min_length=1)
    dimension: int = Field(gt=0)
    distance_metric: PhysicalDistanceMetric
    normalization: str = Field(min_length=1)
    embedding_bundle_count: int = Field(gt=0)
    materialization_count: int = Field(gt=0)

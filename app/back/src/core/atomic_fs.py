"""Escritura determinista de artefactos con promoción atómica staging→final.

Extraído de ``chunking.infrastructure.filesystem_chunk_repository`` (Fase 3) para
que la lane legacy (``FilesystemChunkBundleRepository.replace``) y el sellado de
plataforma (``SealedChunkStore.stage_and_seal``) compartan exactamente la misma
serialización y la misma promoción atómica, sin duplicar la lógica (DRY).

La serialización es **byte-idéntica** a la histórica: ``ensure_ascii=True`` y
``sort_keys=True`` en ambos casos, con salto de línea final. No introducir cambios
de formato aquí sin revisar los golden/tests que dependen de esos bytes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import os
from pathlib import Path
from typing import Any


def write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    """Escribe filas JSONL ordenadas y ASCII, con salto de línea final.

    Bytes idénticos a la escritura histórica del repositorio de chunking.
    """

    payload = "\n".join(
        json.dumps(row, ensure_ascii=True, sort_keys=True) for row in rows
    )
    path.write_text(payload + "\n", encoding="utf-8")


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Escribe un JSON indentado, ordenado y ASCII, con salto de línea final."""

    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def promote_atomically(moves: Sequence[tuple[Path, Path]], *, marker: Path) -> None:
    """Promueve pares ``(staged, final)`` con ``os.replace``, dejando el marker al final.

    ``marker`` es el archivo que un lector usa como prueba de commit (p. ej. el
    metadata de un bundle o su ``checksums.json``). Se elimina primero y debe ser
    el último par de ``moves``, de modo que un fallo a mitad de promoción nunca
    deje un marker apuntando a datos parciales. Cada ``os.replace`` es atómico en
    el mismo sistema de archivos.

    Args:
        moves: Pares ``(origen_staged, destino_final)`` en orden de promoción; el
            último debe ser el ``marker``.
        marker: Archivo final que actúa como indicador de commit.
    """

    if marker.exists():
        marker.unlink()
    for stage, final in moves:
        os.replace(stage, final)

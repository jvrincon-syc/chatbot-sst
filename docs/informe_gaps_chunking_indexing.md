# Informe Formal de Gaps: Integración entre Chunking e Indexing

## 1. Objetivo
Garantizar que el módulo de chunking constituya una fase independiente, canónica y auditable del pipeline, y que la indexación consuma sus resultados sin volver a fragmentar, reconstruir o alterar los chunks.

## 2. Alcance
- Separación efectiva entre chunking e indexación
- Integración del proceso formal de chunking
- Preservación intégra de textos y metadatos
- Consistencia de contratos, estructuras y versiones
- Eliminación de codigos legacy
- Trazabilidad entre doc normalizado y chunks indexados

## 3. Diagnóstico
La архитектура de chunking existe pero no gobierna el pipeline. Indexing reejecuta chunking en memoria (via `structure_aware.py:19`, `pipeline_factory.py:145`) en lugar de consumir resultados previos de data/chunks.

## 4. Gaps Identificados
1. **GAP-CHK-001**
   - *Severidad:* Crítica
   - *Problema:* Indexing no usa ChunkBundle de chunking formal
   - *Impacto:* Dos ejecuciones diferentes pueden dar resultados divergentes
   - *Corrección:* Indexing deberá recibir ValidatedChunkBundle desde/services/chunking/

2. **GAP-CHK-002**
   - *Severidad:* Crítica
   - *Problema:* Chunking ejecuta inline dentro de indexing
   - *Impacto:* Acople técnico y imposibilidad de validar fluxos separadamente
   - *Corrección:* Crear frontera clara: docs_normalized -> ChunkingOrchestrator -> ValidatedChunkBundle -> IndexingService
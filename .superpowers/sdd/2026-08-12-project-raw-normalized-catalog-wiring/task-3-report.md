# Task 3 Report: blocked

## Estado

Task 3 no se implemento porque el `HEAD` actual no contiene los contratos
obligatorios de Task 2 y el write set de esta tarea prohbe crearlos o
modificarlos.

## Conflicto brief vs HEAD

El brief de Task 3 exige que los adapters consuman estos simbolos:

- `RawArtifactCatalogRepository`
- `NormalizedArtifactCatalogRepository`
- `RawDocumentArtifactRecord`
- `NormalizedDocumentArtifactRecord`

En `HEAD`, la ruta esperada
`app/back/src/rag_platform/domain/artifact_catalog.py` no existe. La busqueda
en `app/back/src` y `app/back/tests` tampoco encontro esas definiciones. Por
lo tanto, no es posible escribir una prueba de comportamiento ni un adapter
tipado que cumpla el contrato sin editar el write set exclusivo de Task 2.

Se priorizo `HEAD`, como ordena el encargo. No se creo un contrato alternativo
ni se usaron `dict` o tipos locales como sustituto, pues eso desalinearia los
adapters de los puertos de aplicacion que Task 3 debe consumir.

## Base vigente observada

- `migrations/20260812_01_create_project_raw_and_normalized_artifact_catalogs.sql`
  existe en el arbol de trabajo y se trato como base vigente, sin redisenarla.
- La migracion esta sin seguimiento y existen otros cambios ajenos en el
  arbol de trabajo; no se modificaron ni se revirtieron.
- `artifact_repositories.py` ya contiene el sealed chunk/build ledger y no
  fue modificado.

## TDD y verificacion

No se agrego una prueba fallida: hacerlo requeriria importar los registros y
puertos inexistentes, y no se puede completar el ciclo red-green dentro del
write set permitido. No se ejecutaron pruebas focalizadas, ya que no hay una
implementacion valida que verificar.

## Self-review

- Alcance: sin cambios funcionales fuera del reporte requerido.
- Arquitectura: se preserva la separacion entre identidad logica y catalogos
  fisicos; no se introducen sustitutos incompatibles.
- Seguridad: no se tocaron documentos, secretos ni datos persistidos.
- Reversibilidad: el reporte es aditivo; no hay migraciones ni codigo para
  revertir.

## Desbloqueo requerido

Incorporar primero Task 2 en `HEAD` (al menos
`rag_platform/domain/artifact_catalog.py` y sus puertos). Luego Task 3 puede
crear los adapters, la migracion de indices FK y sus pruebas focalizadas sin
violar el write set.

# chatbot-sst

## Instalación rápida

Requisitos previos:
- Python 3.12.x
- Node.js 18 o superior
- npm

Pasos para instalar y configurar el proyecto en cualquier máquina:

1. Clona el repositorio y entra a la carpeta del proyecto.
2. Ejecuta:
   - macOS / Linux: `npm run setup`
   - Windows PowerShell: `npm run setup`
3. El comando crea un entorno virtual en `.venv`, instala las dependencias Python necesarias en modo editable y genera `secrets.env` a partir de `secrets.example.env`.
4. Activa el entorno virtual:
   - macOS / Linux: `source .venv/bin/activate`
   - Windows PowerShell: `.venv\Scripts\Activate.ps1`
   - Windows CMD: `.venv\Scripts\activate.bat`
5. Si necesitas instalar dependencias adicionales de OCR en macOS, puedes ejecutar:
   - `npm run setup:ocr:mac`

## Entornos virtuales de Python

Este repositorio se trabaja con dos entornos virtuales locales distintos. No deben
copiarse ni reutilizarse entre sistemas operativos, porque sus ejecutables y
paquetes compilados dependen de la plataforma donde fueron creados.

| Entorno | Uso | Sistema | Python | Activación |
| --- | --- | --- | --- | --- |
| `.venv` | Máquina personal | macOS | 3.12.10 (Homebrew) | `source .venv/bin/activate` |
| `.venv_windows_trabajo` | Equipo de trabajo | Windows | 3.12.10 (instalador oficial de Python) | `.venv_windows_trabajo\Scripts\Activate.ps1` |

Los dos entornos tienen `include-system-site-packages = false`: están aislados de
los paquetes instalados globalmente. Aunque actualmente usan la misma versión de
Python, sus rutas y binarios son diferentes:

- macOS usa `/usr/local/opt/python@3.12/bin/python3.12`.
- Windows usa
  `C:\Users\jvrincon\AppData\Local\Programs\Python\Python312\python.exe`.

El proyecto admite Python `>=3.12,<3.13`, según `pyproject.toml`,
`.python-version` y `package.json`. Se recomienda mantener Python 3.12.10 en las
dos máquinas para reducir diferencias durante el desarrollo y las pruebas.

### Paquetes del proyecto

Los mismos rangos de dependencias aplican a ambos entornos:

| Paquete | Rango admitido | Instalado en `.venv_windows_trabajo` |
| --- | --- | --- |
| `numpy` | `>=1.26,<2.3` | 2.2.6 |
| `opencv-python-headless` | `>=4.9,<5` | 4.13.0.92 |
| `pdfplumber` | `>=0.11,<0.12` | 0.11.9 |
| `Pillow` | `>=10,<12` | 11.3.0 |
| `pydantic` | `>=2.0,<2.11` | 2.10.6 |
| `pypdf` | `>=4,<6` | 5.9.0 |
| `pypdfium2` | `>=4.30,<5` | 4.30.0 |
| `pytesseract` | `>=0.3,<0.4` | 0.3.13 |
| `pytest` (desarrollo) | `>=8.0,<9` | 8.4.2 |

La columna de Windows refleja las versiones instaladas actualmente, no un
archivo de bloqueo. En la copia de `.venv` disponible en Windows no están los
metadatos de paquetes del entorno macOS; para consultar sus versiones exactas
hay que ejecutar en la Mac:

```bash
source .venv/bin/activate
python --version
python -m pip list
```

Para comprobar el entorno Windows:

```powershell
.\.venv_windows_trabajo\Scripts\Activate.ps1
python --version
python -m pip list
```

### Diferencias operativas

- Las dependencias Python declaradas son las mismas; lo que cambia es el binario
  de Python y cualquier rueda nativa instalada para macOS o Windows.
- En macOS, las herramientas OCR del sistema se instalan con
  `npm run setup:ocr:mac`, que usa Homebrew para instalar `ocrmypdf`,
  `tesseract` y `tesseract-lang`.
- En Windows, `ocrmypdf` 16.13.0 está instalado en
  `.venv_windows_trabajo`; Tesseract y otras dependencias externas deben estar
  disponibles en Windows y en `PATH` cuando el pipeline las necesite.
- `npm run setup` y los comandos `npm run python -- ...` usan siempre `.venv`.
  En el equipo de trabajo, si se desea conservar
  `.venv_windows_trabajo`, se debe activarlo y ejecutar directamente
  `python -m pytest ...` o `python scripts/...`. Ejecutar `npm run setup`
  crea o reemplaza `.venv`, no `.venv_windows_trabajo`.
- Los entornos virtuales son artefactos locales. Las fuentes de verdad de las
  dependencias son `pyproject.toml`, `requirements.txt` y
  `requirements-dev.txt`.

Comandos útiles:
- `npm run doctor:ocr`
- `npm run test:ingestion`
- `npm run ingestion:inventory`
- `npm run ingestion:run`
- `npm run ingestion:validate`
- `npm run schemas:export`

RAG: si uso rag tengo que usar embedings y usar una bd vectorizada



Parameter-Efficient Fine-Tuning (PEFT / LoRA) seria como el prefix fine tuning(?) de pronto si congelo los pesos de abajo y dejo los de arriba descongelados puedo entrenar un poco mas algún llm local como qwen o llama para que el modelo quede "especializado" con los pdfs y documentos que tengo , la desventaja es que no me podrá citar exactamente la pagina o documento del cual lo saca


Revisar GRAPH RAG  como posible alternativa, revisar si se pueden hacer conexiones entre informacion


RAG con re RANKING 

Arquitectura por agentes: por ej dos agentes que 
Paso de Localización: El modelo busca y extrae textualmente (copiar y pegar) los párrafos relevantes de los PDFs.Paso de Verificación:

Un segundo modelo compara la respuesta final generada contra los párrafos extraídos textualmente para verificar que no se haya inventado ningún dato.

CONSIDERAR: Crear un FAQ donde se haga un prefiltrafo con fuzzy para no tener que hacer toda la consulta completa, de pronto usar REDIS para cachear preguntas frecuentes que no esten en FAQ y agregarlas.

CONSIDERACION 2: CREAR UNA CAPA DE NORMALIZACION PAARA AJUSTAR AL CONTEXTO 

CONSIDERACION 3: USAR PARENT AND CHILD CON OVERLAP PARA EL CHUNKING

CONSIDERACION 4: verificar que ocr usar como rapidOCR o depronto tesseract.

CONSIDERACION 5: para embedding considerar BAAI/BGE-M3,Voyage-4,
Cohere Embed v4.0

CONSIDERACION 6: usar QDRANT o pgvector en posgrest

CONSIDERACION 7: CUANTIZAR VECTORES

CONSIDERACION 8: METADATOS PARA LOS CHUNKS PARA PREFILTRADO; CLASIFICA TEXTOS


REVISAR SI ALGUNA PLANTILLA DE MASTRA ME SIRVE (https://mastra.ai/templates/chat-with-pdf) (https://mastra.ai/templates/docs-chatbot)


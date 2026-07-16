# chatbot-sst

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


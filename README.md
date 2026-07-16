# chatbot-sst

RAG: si uso rag tengo que usar embedings y usar una bd vectorizada



Parameter-Efficient Fine-Tuning (PEFT / LoRA) seria como el prefix fine tuning(?) de pronto si congelo los pesos de abajo y dejo los de arriba descongelados puedo entrenar un poco mas algún llm local como qwen o llama para que el modelo quede "especializado" con los pdfs y documentos que tengo , la desventaja es que no me podrá citar exactamente la pagina o documento del cual lo saca


Revisar GRAPH RAG  como posible alternativa, revisar si se pueden hacer conexiones entre informacion


RAG con re RANKING 

Arquitectura por agentes: por ej dos agentes que 
Paso de Localización: El modelo busca y extrae textualmente (copiar y pegar) los párrafos relevantes de los PDFs.Paso de Verificación:

Un segundo modelo compara la respuesta final generada contra los párrafos extraídos textualmente para verificar que no se haya inventado ningún dato.

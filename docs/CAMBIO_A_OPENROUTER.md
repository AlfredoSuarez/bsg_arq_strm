# Cambio de proveedor: OpenRouter + NVIDIA Nemotron 3 Ultra

## Qué cambia

El proyecto sustituye `langchain-google-genai` por `langchain-openai`. No se está usando OpenAI como proveedor: `ChatOpenAI` se aprovecha como adaptador compatible con la API de OpenAI y se configura con `base_url="https://openrouter.ai/api/v1"`.

La arquitectura MCP, las tools SQL, la memoria de corto plazo, Streamlit y Claude Desktop no cambian. Cambian únicamente:

- la dependencia `langchain-openai`;
- la variable `OPENROUTER_API_KEY`;
- el nombre de modelo configurado en `OPENROUTER_MODEL`;
- el endpoint del modelo, que pasa a ser OpenRouter.

## Variables de entorno

```env
OPENROUTER_API_KEY=tu_clave_personal
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
```

## Por qué el modelo queda configurable

Los modelos marcados como gratuitos pueden tener límites de uso, disponibilidad variable por proveedor o cambios de identificador. El laboratorio usa el slug solicitado como valor por defecto, pero `OPENROUTER_MODEL` permite cambiarlo sin editar el código.

## Impacto didáctico

El cambio demuestra que LangChain desacopla la lógica de agente de la ruta de acceso al modelo. El agente continúa usando las mismas tools MCP y la misma memoria: cambia el proveedor y las credenciales, no el diseño de integración.

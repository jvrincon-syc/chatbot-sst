function looksLikeHtml(text) {
    const trimmed = text.trimStart().toLowerCase();
    return (trimmed.startsWith("<!doctype") ||
        trimmed.startsWith("<html") ||
        trimmed.startsWith("<head") ||
        trimmed.startsWith("<body") ||
        trimmed.startsWith("<!--"));
}
async function readResponseText(response) {
    if (typeof response.text === "function") {
        return response.text();
    }
    if (typeof response.json === "function") {
        const payload = await response.json();
        return typeof payload === "string" ? payload : JSON.stringify(payload);
    }
    return "";
}
export async function readJsonResponse(response) {
    const text = await readResponseText(response);
    const trimmed = text.trimStart();
    try {
        return (trimmed.length > 0 ? JSON.parse(text) : null);
    }
    catch (error) {
        if (looksLikeHtml(trimmed)) {
            throw new Error("La API devolvio HTML en lugar de JSON. Verifica que el backend este levantado y que el front use el proxy de /api.");
        }
        throw new Error("La API devolvio una respuesta que no es JSON valido.");
    }
}

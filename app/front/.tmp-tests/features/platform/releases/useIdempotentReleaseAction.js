import { useCallback, useRef } from "react";
import { createIdempotencyKey } from "../../../shared/api/apiClient.js";
import { mapPipelineError } from "../../../shared/api/errorMapping.js";
// D7 — Ciclo de vida de la Idempotency-Key por INTENCIÓN lógica del operador (no
// por request). Invariantes:
//   - Una clave por intención (`intent`, p. ej. "build:rel_1"). Vive SOLO en
//     memoria: nunca localStorage ni persistencia.
//   - Un reintento de la MISMA intención (mismo botón tras un fallo recuperable)
//     reusa la MISMA clave → replay seguro server-side.
//   - Solo una respuesta TERMINAL (éxito o fallo definitivo) o un abandono
//     explícito rotan la clave; la próxima acción de esa intención acuña una nueva.
//   - Un `409 IDEMPOTENCY_KEY_CONFLICT` NO rota la clave automáticamente: hacerlo
//     habilitaría un replay silencioso con clave nueva. El operador debe actuar.
function shouldRotateKeyOnError(error) {
    const mapped = mapPipelineError(error);
    // Conflicto de idempotencia: mantener la clave (no autoregenerar ni replay).
    if (mapped.code === "IDEMPOTENCY_KEY_CONFLICT") {
        return false;
    }
    // Recuperable (red/timeout/503/429/executor busy): el mismo intento puede
    // reintentar con la MISMA clave.
    if (mapped.retryable) {
        return false;
    }
    // Fallo definitivo del intento (transición inválida, build demasiado grande,
    // operación idempotente fallida, validación): el intento se cierra; la próxima
    // acción acuña una clave nueva.
    return true;
}
export function useIdempotentReleaseAction() {
    // Clave viva por intención. `useRef`: sobrevive re-renders sin re-render propio.
    const keysRef = useRef(new Map());
    const run = useCallback(async (intent, action) => {
        const key = keysRef.current.get(intent) ?? createIdempotencyKey("platform");
        keysRef.current.set(intent, key);
        try {
            const result = await action({ idempotencyKey: key });
            // Éxito = terminal: la próxima intención acuña clave nueva.
            keysRef.current.delete(intent);
            return result;
        }
        catch (error) {
            if (shouldRotateKeyOnError(error)) {
                keysRef.current.delete(intent);
            }
            throw error;
        }
    }, []);
    // Abandono explícito / nueva intención: descarta la clave viva de una intención.
    const abandon = useCallback((intent) => {
        keysRef.current.delete(intent);
    }, []);
    return { run, abandon };
}

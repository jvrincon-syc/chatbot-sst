import type {
  RetrievalProfileStatus,
  RetrievalReadiness,
  RetrievalStageState,
} from "./retrievalTypes.js";

// Retrieval is read-only and unavailable until activation produces a
// retrieval_profile_id. While a profile exists but its status has not loaded,
// the stage is "loading"; once loaded it is "ready" or "blocked" per readiness.
export function deriveRetrievalStageState(input: {
  retrievalProfileId: string | null;
  statusPayload: RetrievalProfileStatus | null;
}): RetrievalStageState {
  if (!input.retrievalProfileId) {
    return { stage: "unavailable", blockingReasons: [] };
  }
  if (!input.statusPayload) {
    return { stage: "loading", blockingReasons: [] };
  }
  const { readiness } = input.statusPayload;
  if (readiness.ready) {
    return { stage: "ready", blockingReasons: [] };
  }
  return { stage: "blocked", blockingReasons: readiness.blockingReasons };
}

// Validation can only run when a profile exists and its query engine is
// available. Runtime and readiness are independent: the engine can be healthy
// while readiness is blocked, so validation gates on runtime, not readiness.
export function retrievalCanValidate(status: RetrievalProfileStatus): boolean {
  return Boolean(status.profile.retrievalProfileId) && status.runtime.queryEngineAvailable;
}

export function retrievalReadinessBlocked(readiness: RetrievalReadiness): boolean {
  return !readiness.ready;
}

export function retrievalValidationStatusLabel(status: string): string {
  if (status === "pending") return "Pendiente";
  if (status === "passed") return "Aprobada";
  if (status === "failed") return "Fallida";
  if (status === "compatibility_not_proven") return "Compatibilidad no probada";
  return "Desconocido";
}

export function retrievalValidationStatusTone(
  status: string,
): "neutral" | "success" | "warning" | "danger" {
  if (status === "passed") return "success";
  if (status === "pending") return "warning";
  if (status === "failed") return "danger";
  if (status === "compatibility_not_proven") return "danger";
  return "neutral";
}

export function retrievalRuntimeStatusLabel(status: string): string {
  if (status === "never_run") return "Sin ejecutar";
  if (status === "ok") return "Correcto";
  if (status === "failed") return "Fallido";
  if (status === "blocked") return "Bloqueado";
  return "Desconocido";
}

export function retrievalRuntimeStatusTone(
  status: string,
): "neutral" | "success" | "warning" | "danger" {
  if (status === "ok") return "success";
  if (status === "never_run") return "neutral";
  if (status === "failed" || status === "blocked") return "danger";
  return "neutral";
}

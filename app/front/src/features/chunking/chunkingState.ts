import type { ChunkingRunSummary } from "./chunkingTypes.js";

export function parseChunkingDocumentIds(raw: string): string[] {
  const seen = new Set<string>();
  const values: string[] = [];
  for (const token of raw.split(/[\s,]+/)) {
    const value = token.trim();
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    values.push(value);
  }
  return values;
}

export function createChunkingIdempotencyKey(): string {
  const cryptoObject = globalThis.crypto as Crypto | undefined;
  if (cryptoObject?.randomUUID) {
    return `chunking-${cryptoObject.randomUUID()}`;
  }
  return `chunking-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function chunkingRunProgressPercent(run: Pick<ChunkingRunSummary, "requestedDocuments" | "completedDocuments">): number {
  if (run.requestedDocuments <= 0) {
    return 0;
  }
  return Math.min(100, Math.round((run.completedDocuments / run.requestedDocuments) * 100));
}

export function chunkingRunStatusLabel(status: string): string {
  if (status === "queued") return "En cola";
  if (status === "running") return "En ejecucion";
  if (status === "completed") return "Completada";
  if (status === "completed_with_warnings") return "Completada con alertas";
  if (status === "interrupted") return "Interrumpida";
  if (status === "failed") return "Fallida";
  return "Desconocido";
}

export function chunkingRunStatusTone(status: string): "neutral" | "success" | "warning" | "danger" {
  if (status === "completed") return "success";
  if (status === "completed_with_warnings" || status === "queued" || status === "interrupted") {
    return "warning";
  }
  if (status === "failed") return "danger";
  return "neutral";
}

export function chunkingRunIsTerminalStatus(status: string): boolean {
  return (
    status === "completed" ||
    status === "completed_with_warnings" ||
    status === "failed" ||
    status === "interrupted"
  );
}

export function chunkingScopeLabel(scope: string): string {
  return scope === "corpus" ? "Corpus" : "Documentos";
}

export function chunkingPaginationLabel(page: number, totalPages: number, totalItems: number): string {
  if (totalItems === 0) {
    return "Sin resultados";
  }
  return `Pagina ${page} de ${totalPages} · ${totalItems} items`;
}

export function chunkingProfileSummary(profile: {
  childMinTokens: number;
  childTargetTokens: number;
  childMaxTokens: number;
  overlapRatio: number;
  overlapMinTokens: number;
  overlapMaxTokens: number;
}): string {
  const overlapPercent = Math.round(profile.overlapRatio * 100);
  return `Min ${profile.childMinTokens} · Target ${profile.childTargetTokens} · Max ${profile.childMaxTokens} · Overlap ${overlapPercent}% (${profile.overlapMinTokens}-${profile.overlapMaxTokens})`;
}

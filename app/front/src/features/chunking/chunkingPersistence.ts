import { DEFAULT_CHUNKING_PROFILE_ID, createChunkingIdempotencyKey, type ChunkingFormState } from "./chunkingState.js";

const STORAGE_KEY = "chatbot-sst.chunking.workspace.v1";

type ChunkingWorkspaceSnapshot = {
  scope: ChunkingFormState["scope"];
  documentIdsInput: string;
  profileId: string;
  force: boolean;
};

function isScope(value: unknown): value is ChunkingFormState["scope"] {
  return value === "documents" || value === "corpus";
}

function toString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function toBoolean(value: unknown): boolean {
  return typeof value === "boolean" ? value : false;
}

function toSnapshot(value: unknown): ChunkingWorkspaceSnapshot | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }

  const record = value as Record<string, unknown>;
  return {
    scope: isScope(record.scope) ? record.scope : "corpus",
    documentIdsInput: toString(record.documentIdsInput),
    profileId: toString(record.profileId) || DEFAULT_CHUNKING_PROFILE_ID,
    force: toBoolean(record.force),
  };
}

export function readChunkingWorkspaceSnapshot(): ChunkingWorkspaceSnapshot | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }
    return toSnapshot(JSON.parse(raw));
  } catch {
    return null;
  }
}

export function createChunkingWorkspaceFormState(
  snapshot: ChunkingWorkspaceSnapshot | null,
): ChunkingFormState {
  return {
    scope: snapshot?.scope ?? "corpus",
    documentIdsInput: snapshot?.documentIdsInput ?? "",
    profileId: snapshot?.profileId ?? DEFAULT_CHUNKING_PROFILE_ID,
    force: snapshot?.force ?? false,
    idempotencyKey: createChunkingIdempotencyKey(),
  };
}

export function writeChunkingWorkspaceSnapshot(form: ChunkingFormState): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    const snapshot: ChunkingWorkspaceSnapshot = {
      scope: form.scope,
      documentIdsInput: form.documentIdsInput,
      profileId: form.profileId,
      force: form.force,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    // Ignore storage failures. The workspace still functions without persistence.
  }
}

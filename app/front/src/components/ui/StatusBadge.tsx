// Chip de estado compartido: mismo markup y tonos que los `.ui-status-chip`
// dispersos por los workspaces, una sola definición. El estado se comunica con
// TEXTO además del tono (a11y §8: nunca solo color).
export type StatusTone = "neutral" | "success" | "warning" | "danger";

export function StatusBadge({ label, tone }: { label: string; tone: StatusTone }) {
  return <span className={`ui-status-chip ${tone}`}>{label}</span>;
}

export type MetricTone = "neutral" | "success" | "warning" | "danger";

// Tarjeta de metrica compartida por el resumen del dashboard y por las
// pantallas de pipeline: mismo markup, mismos tonos, una sola definicion.
export function MetricCard({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: string | number;
  icon: JSX.Element;
  tone: MetricTone;
}) {
  return (
    <article className={`metric-card ${tone}`}>
      <div className="metric-icon">{icon}</div>
      <div>
        <span>{label}</span>
        <strong>{typeof value === "number" ? value.toLocaleString("es-CO") : value}</strong>
      </div>
    </article>
  );
}

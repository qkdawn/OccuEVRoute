interface MetricProps {
  label: string;
  value: string;
}

export function Metric({ label, value }: MetricProps) {
  return (
    <div className="ui-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

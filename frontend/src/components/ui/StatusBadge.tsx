type BadgeTone = "success" | "warning" | "danger" | "neutral" | "route";

interface StatusBadgeProps {
  children: string;
  tone?: BadgeTone;
}

export function StatusBadge({ children, tone = "neutral" }: StatusBadgeProps) {
  return <span className={`status-badge status-badge-${tone}`}>{children}</span>;
}

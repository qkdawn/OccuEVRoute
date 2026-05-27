import type { ReactNode } from "react";

interface PanelProps {
  children: ReactNode;
  eyebrow: string;
  isOpen: boolean;
  onToggle: () => void;
  summary: string;
  title: string;
}

export function Panel({ children, eyebrow, isOpen, onToggle, summary, title }: PanelProps) {
  return (
    <section className="ui-panel">
      <button type="button" className="panel-trigger" aria-expanded={isOpen} onClick={onToggle}>
        <span>
          <small>{eyebrow}</small>
          <strong>{title}</strong>
        </span>
        <em>{summary}</em>
      </button>
      {isOpen && <div className="panel-body">{children}</div>}
    </section>
  );
}

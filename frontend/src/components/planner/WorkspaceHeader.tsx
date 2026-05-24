import { Button } from "../ui";

interface WorkspaceHeaderProps {
  onReset: () => void;
}

export function WorkspaceHeader({ onReset }: WorkspaceHeaderProps) {
  return (
    <header className="workspace-header">
      <div>
        <p className="eyebrow">OccuEVRoute</p>
        <h1>EV charging route planner</h1>
      </div>
      <Button variant="secondary" onClick={onReset}>
        Reset
      </Button>
    </header>
  );
}

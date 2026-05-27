export function WorkspaceHeader() {
  return (
    <header className="workspace-header">
      <div className="workspace-mark" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div className="workspace-title">
        <p className="eyebrow">EV charging route planner</p>
        <h1>OccuEVRoute</h1>
      </div>
    </header>
  );
}

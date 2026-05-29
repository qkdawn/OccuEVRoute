import logo from "../../assets/occuevroute-logo.jpg";

export function WorkspaceHeader() {
  return (
    <header className="workspace-header">
      <img className="workspace-mark" src={logo} alt="" aria-hidden="true" />
      <div className="workspace-title">
        <p className="eyebrow">EV charging route planner</p>
        <h1>OccuEVRoute</h1>
      </div>
    </header>
  );
}

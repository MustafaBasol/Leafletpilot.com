import { Header } from "./Header.jsx";
import { Sidebar } from "./Sidebar.jsx";

export function AppLayout({ currentPath, pageTitle, onLogout, sessionVersion, children }) {
  return (
    <div className="app-shell">
      <Sidebar currentPath={currentPath} sessionVersion={sessionVersion} />
      <main className="main-shell">
        <Header pageTitle={pageTitle} onLogout={onLogout} sessionVersion={sessionVersion} />
        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}

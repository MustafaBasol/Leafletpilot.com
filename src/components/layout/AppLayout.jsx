import { Header } from "./Header.jsx";
import { Sidebar } from "./Sidebar.jsx";

export function AppLayout({ currentPath, pageTitle, onLogout, children }) {
  return (
    <div className="app-shell">
      <Sidebar currentPath={currentPath} />
      <main className="main-shell">
        <Header pageTitle={pageTitle} onLogout={onLogout} />
        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}

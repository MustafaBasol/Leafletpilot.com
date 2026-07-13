import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";

export function PlatformTemplates() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  async function load() { try { const result = await platformApi.listTemplates({}); setItems(result.items || []); setError(""); } catch (e) { setError(e.message || "Templates could not be loaded."); } }
  useEffect(() => { load(); }, []);
  async function action(fn) { try { await fn(); await load(); } catch (e) { setError(e.message || "Template action failed."); } }
  async function create() { if (!name.trim()) return; await action(() => platformApi.createTemplate({ name, template_type: "flyer", description: "", minimum_plan: "starter", config_json: { slot_count: 8 } })); setName(""); }
  return <section className="platform-page">
    <header className="platform-page-header"><div><p className="eyebrow">Platform Admin</p><h1>Global templates</h1><p>Manage shared drafts, published versions, and archived templates.</p></div></header>
    {error ? <p className="inline-result inline-result-warning">{error}</p> : null}
    <div className="card" style={{ marginBottom: 20 }}><h2>Create global template</h2><div className="form-row"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Template name" /><button className="button button-primary" onClick={create}>Create draft</button></div></div>
    <div className="platform-table-wrap"><table className="platform-table"><thead><tr><th>Name</th><th>Category</th><th>Version</th><th>Status</th><th>Minimum plan</th><th>Actions</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td>{item.name}</td><td>{item.category || "—"}</td><td>v{item.version}</td><td>{item.status}</td><td>{item.minimum_plan}</td><td><button onClick={() => action(() => platformApi.publishTemplate(item.id))}>Publish</button> <button onClick={() => action(() => platformApi.duplicateTemplate(item.id))}>New version</button> <button onClick={() => action(() => platformApi.archiveTemplate(item.id))}>Archive</button></td></tr>)}</tbody></table></div>
  </section>;
}

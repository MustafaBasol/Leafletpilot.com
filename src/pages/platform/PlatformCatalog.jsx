import { useEffect, useState } from "react";
import { platformApi } from "../../api/platformApi.js";
import { t } from "./platformI18n.js";

export function PlatformCatalog() {
  const [tab, setTab] = useState("categories"); const [rows, setRows] = useState([]); const [search, setSearch] = useState("");
  const [name, setName] = useState(""); const [loading, setLoading] = useState(true); const [error, setError] = useState("");
  const api = tab === "categories" ? platformApi : tab === "brands" ? platformApi : platformApi;
  async function load() { setLoading(true); setError(""); try { const fn = tab === "categories" ? api.listGlobalCategories : tab === "brands" ? api.listGlobalBrands : api.listGlobalProducts; setRows((await fn({ search })).items || []); } catch (e) { setError(e.message); } finally { setLoading(false); } }
  useEffect(() => { load(); }, [tab]);
  async function create() { try { const fn = tab === "categories" ? api.createGlobalCategory : tab === "brands" ? api.createGlobalBrand : api.createGlobalProduct; await fn({ name, aliases: tab === "products" ? [] : undefined }); setName(""); load(); } catch (e) { setError(e.message); } }
  async function deactivate(row) { try { const fn = tab === "categories" ? api.deactivateGlobalCategory : tab === "brands" ? api.deactivateGlobalBrand : api.deactivateGlobalProduct; await fn(row.id); load(); } catch (e) { setError(e.message); } }
  return <section className="platform-page"><div className="page-header"><h1>Global catalog</h1></div><div className="tabs">{["categories", "brands", "products"].map((item) => <button className={tab === item ? "active" : ""} key={item} onClick={() => setTab(item)}>{item}</button>)}</div><div className="toolbar"><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("search")} onKeyDown={(e) => e.key === "Enter" && load()} /><button onClick={load}>{t("search")}</button></div><div className="form-grid"><label>Name<input value={name} onChange={(e) => setName(e.target.value)} /></label><button onClick={create}>Create</button></div>{error && <p className="error-message">{error}</p>}{loading ? <p>{t("loading")}</p> : rows.length === 0 ? <p>No records found.</p> : <table><thead><tr><th>Name</th><th>Active</th><th>Usage</th><th /></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{row.name}</td><td>{row.is_active ? "✓" : "—"}</td><td>{row.usage_count ?? 0}</td><td>{row.is_active && <button onClick={() => deactivate(row)}>Deactivate</button>}</td></tr>)}</tbody></table>}</section>;
}

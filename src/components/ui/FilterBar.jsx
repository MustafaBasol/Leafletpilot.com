import { Icon } from "./Icon.jsx";

export function FilterBar({ searchPlaceholder = "Ara", searchValue, onSearchChange, children }) {
  return (
    <section className="filter-bar">
      <label className="filter-search">
        <Icon name="search" />
        <input aria-label="Ara" placeholder={searchPlaceholder} value={searchValue} onChange={onSearchChange} />
      </label>
      <div className="filter-controls">{children}</div>
    </section>
  );
}

export function FilterChip({ label, value = "Tümü" }) {
  return (
    <button className="filter-chip" type="button">
      <span>{label}</span>
      <strong>{value}</strong>
    </button>
  );
}

export function Checkbox({ label, checked = false, onChange, name }) {
  return (
    <label className="check-row">
      <input name={name} type="checkbox" checked={checked} onChange={onChange} />
      <span>{label}</span>
    </label>
  );
}

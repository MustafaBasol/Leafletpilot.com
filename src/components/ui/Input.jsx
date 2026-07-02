export function Input({ label, placeholder = "", type = "text", value, onChange, name, ...rest }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input name={name} type={type} placeholder={placeholder} value={value} onChange={onChange} {...rest} />
    </label>
  );
}

export function SelectPlaceholder({ label, value = "Seçiniz", onClick }) {
  return (
    <label className="field">
      <span>{label}</span>
      <button className="select-placeholder" type="button" onClick={onClick}>
        {value}
        <span>⌄</span>
      </button>
    </label>
  );
}

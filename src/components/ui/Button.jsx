export function Button({
  children,
  variant = "secondary",
  href,
  className = "",
  type = "button",
  onClick,
  disabled = false,
  ...rest
}) {
  const classes = `button button-${variant} ${className}`.trim();

  if (href) {
    return (
      <a className={classes} href={href} onClick={onClick} aria-disabled={disabled} {...rest}>
        {children}
      </a>
    );
  }

  return (
    <button className={classes} type={type} onClick={onClick} disabled={disabled} {...rest}>
      {children}
    </button>
  );
}

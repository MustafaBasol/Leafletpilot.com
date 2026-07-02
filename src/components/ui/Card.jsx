export function Card({ title, action, className = "", children }) {
  return (
    <section className={`card ${className}`.trim()}>
      {title ? (
        <div className="card-header">
          <h2>{title}</h2>
          {action}
        </div>
      ) : null}
      {children}
    </section>
  );
}

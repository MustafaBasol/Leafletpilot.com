export function MessageFlowPreview({ steps }) {
  return (
    <ol className="message-flow">
      {steps.map((step, index) => (
        <li key={step.title}>
          <span>{index + 1}</span>
          <div>
            <strong>{step.title}</strong>
            <p>{step.detail}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

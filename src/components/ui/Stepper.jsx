export function Stepper({ steps, currentStep }) {
  return (
    <ol className="stepper">
      {steps.map((step, index) => {
        const stepNumber = index + 1;
        const state = stepNumber === currentStep ? "is-current" : stepNumber < currentStep ? "is-done" : "";

        return (
          <li className={state} key={step}>
            <span>{stepNumber}</span>
            <strong>{step}</strong>
          </li>
        );
      })}
    </ol>
  );
}

type OnboardingStepHeadingProps = {
  title: string
  subtitle: string
}

export function OnboardingStepHeading({ title, subtitle }: OnboardingStepHeadingProps) {
  return <header className="onboarding-heading">
    <h2 id="onboarding-step-heading">{title}</h2>
    <p>{subtitle}</p>
  </header>
}

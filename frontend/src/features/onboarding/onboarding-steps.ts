export const ONBOARDING_STEPS = [
  { id: 'welcome', label: 'Welcome' },
  { id: 'components', label: 'Get ready' },
  { id: 'settings', label: 'Your settings' },
  { id: 'add-media', label: 'Add a file' },
  { id: 'process-media', label: 'Process safely' },
  { id: 'finish', label: 'Finish' },
] as const

export type OnboardingStepId = typeof ONBOARDING_STEPS[number]['id']

export function onboardingStepIndex(step: string): number {
  const index = ONBOARDING_STEPS.findIndex((candidate) => candidate.id === step)
  return index === -1 ? 0 : index
}

export function nextOnboardingStep(step: number): OnboardingStepId {
  return ONBOARDING_STEPS[Math.min(step + 1, ONBOARDING_STEPS.length - 1)].id
}

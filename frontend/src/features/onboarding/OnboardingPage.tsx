import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, Check, ShieldCheck } from 'lucide-react'
import { desktopClient } from '../../services/desktop-client'
import type { Capabilities, Settings } from '../../types/domain'
import type { DictionaryController } from '../dictionary/useDictionary'
import type { QueueController } from '../queue/useQueue'
import type { SettingsController } from '../settings/useSettingsController'
import { AddMediaStep } from './AddMediaStep'
import { ComponentsStep } from './ComponentsStep'
import { FinishStep } from './FinishStep'
import { InitialSettingsStep } from './InitialSettingsStep'
import { ONBOARDING_STEPS, nextOnboardingStep, onboardingStepIndex } from './onboarding-steps'
import { ProcessMediaStep } from './ProcessMediaStep'
import { WelcomeStep } from './WelcomeStep'
import './onboarding.css'

type OnboardingPageProps = {
  settings: SettingsController
  capabilities: Capabilities | null
  checking: boolean
  capabilityBusy: boolean
  dictionary: DictionaryController
  queue: QueueController
  onReviewInstall: (components: string[]) => void
  onLocateExisting: (component: 'ffmpeg' | 'whisper_model' | 'ytdlp') => void
  onCheckAgain: () => void
  onFinished: () => void
  onError: (message: string) => void
}

export function OnboardingPage({
  settings,
  capabilities,
  checking,
  capabilityBusy,
  dictionary,
  queue,
  onReviewInstall,
  onLocateExisting,
  onCheckAgain,
  onFinished,
  onError,
}: OnboardingPageProps) {
  const initialSettings = settings.draft
  const [step, setStep] = useState(() => initialSettings?.onboarding.completed
    ? 0
    : onboardingStepIndex(initialSettings?.onboarding.last_step ?? 'welcome'))
  const [draft, setDraft] = useState<Settings | null>(initialSettings)
  const [dictionaryPrepared, setDictionaryPrepared] = useState(initialSettings?.onboarding.completed ?? false)
  const [firstFileSource, setFirstFileSource] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const stepRegion = useRef<HTMLDivElement>(null)

  useEffect(() => {
    stepRegion.current?.focus()
  }, [step])

  if (!draft) return <div className="loading-row">Loading setup</div>
  const currentDraft = draft
  const requiredComponentsReady = Boolean(
    capabilities?.ffmpeg
    && capabilities.ffprobe
    && capabilities.whisper
    && capabilities.whisper_model_ready
    && capabilities.whisper_model === 'large-v3',
  )
  const stepId = ONBOARDING_STEPS[step].id

  const updateDraft = <K extends keyof Settings>(group: K, value: Settings[K]) => {
    setDraft((current) => current ? { ...current, [group]: value } : current)
  }

  const saveAndAdvance = async () => {
    if (stepId === 'components' && !requiredComponentsReady) return
    if (stepId === 'settings' && !dictionaryPrepared) return
    const next = nextOnboardingStep(step)
    const nextDraft: Settings = {
      ...currentDraft,
      onboarding: { ...currentDraft.onboarding, last_step: next },
    }
    setSaving(true)
    const saved = await settings.saveDraft(nextDraft)
    setSaving(false)
    if (!saved) return
    setDraft(nextDraft)
    setStep((current) => Math.min(current + 1, ONBOARDING_STEPS.length - 1))
  }

  const chooseDirectory = async (key: keyof Settings['directories']) => {
    try {
      const selected = await desktopClient.selectDirectory(currentDraft.directories[key])
      if (selected) updateDraft('directories', { ...currentDraft.directories, [key]: selected })
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  const finish = async () => {
    const finishedDraft: Settings = {
      ...currentDraft,
      onboarding: { completed: true, last_step: 'finish' },
    }
    setSaving(true)
    const saved = await settings.saveDraft(finishedDraft)
    setSaving(false)
    if (saved) onFinished()
  }

  return <section className="page onboarding-page" aria-labelledby="onboarding-title">
    <aside className="onboarding-rail">
      <span className="eyebrow">First-run setup</span>
      <h1 id="onboarding-title">Make it yours</h1>
      <ol>
        {ONBOARDING_STEPS.map(({ id, label }, index) => <li key={id} className={index === step ? 'active' : index < step ? 'complete' : undefined} aria-current={index === step ? 'step' : undefined}>
          <span>{index < step ? <Check size={13} /> : index + 1}</span>{label}
        </li>)}
      </ol>
      <small>Your choices stay on this computer.</small>
    </aside>

    <div className="onboarding-workspace">
      <div className="onboarding-step" ref={stepRegion} tabIndex={-1} aria-labelledby="onboarding-step-heading">
        {stepId === 'welcome' && <WelcomeStep />}
        {stepId === 'components' && <ComponentsStep capabilities={capabilities} checking={checking} busy={capabilityBusy} onReviewInstall={onReviewInstall} onLocateExisting={onLocateExisting} onCheckAgain={onCheckAgain} />}
        {stepId === 'settings' && <InitialSettingsStep draft={currentDraft} dictionary={dictionary} dictionaryPrepared={dictionaryPrepared} onDictionaryPrepared={() => setDictionaryPrepared(true)} onChange={updateDraft} onChooseDirectory={(key) => void chooseDirectory(key)} />}
        {stepId === 'add-media' && <AddMediaStep queue={queue} settings={currentDraft} onAdded={setFirstFileSource} />}
        {stepId === 'process-media' && <ProcessMediaStep source={firstFileSource} queue={queue} settings={currentDraft} capabilities={capabilities} />}
        {stepId === 'finish' && <FinishStep settings={currentDraft} capabilities={capabilities} dictionaryPrepared={dictionaryPrepared} />}
      </div>
      <footer className="onboarding-actions">
        <button className="button secondary" disabled={step === 0 || saving} onClick={() => setStep((current) => current - 1)}><ArrowLeft size={16} />Back</button>
        <span aria-live="polite">Step {step + 1} of {ONBOARDING_STEPS.length}: {ONBOARDING_STEPS[step].label}</span>
        {stepId === 'finish'
          ? <button className="button primary" disabled={saving} onClick={() => void finish()}><ShieldCheck size={16} />Finish setup</button>
          : <button className="button primary" disabled={saving || (stepId === 'components' && !requiredComponentsReady) || (stepId === 'settings' && !dictionaryPrepared)} onClick={() => void saveAndAdvance()}>Save & Continue<ArrowRight size={16} /></button>}
      </footer>
    </div>
  </section>
}

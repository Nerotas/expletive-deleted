import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, Check, ShieldCheck } from 'lucide-react'
import { desktopClient } from '../../services/desktop-client'
import type { Capabilities, Settings } from '../../types/domain'
import type { DictionaryController } from '../dictionary/useDictionary'
import type { QueueController } from '../queue/useQueue'
import type { SettingsController } from '../settings/useSettingsController'
import { applySettingChanges, settingChanges, type WizardProgress } from '../settings/settings-transactions'
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
  // A replay starts from persisted values, independently of unsaved normal
  // Settings edits. Background query refreshes never replace this wizard draft.
  const initialSettings = settings.persistedSnapshot?.settings ?? null
  const [step, setStep] = useState(() => initialSettings?.onboarding.completed
    ? 0
    : onboardingStepIndex(initialSettings?.onboarding.last_step ?? 'welcome'))
  const [draft, setDraft] = useState<Settings | null>(initialSettings)
  const [dictionaryPrepared, setDictionaryPrepared] = useState(initialSettings?.onboarding.completed ?? false)
  const [firstFileSource, setFirstFileSource] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const baseline = useRef(settings.persistedSnapshot)
  const latestDraft = useRef(initialSettings)
  const mounted = useRef(true)
  const saveInFlight = useRef(false)
  const stepRegion = useRef<HTMLDivElement>(null)

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  useEffect(() => {
    stepRegion.current?.focus()
  }, [step])

  if (!draft) return <div className="loading-row">Loading setup</div>
  const currentDraft = draft
  const stepId = ONBOARDING_STEPS[step].id

  const updateDraft = <K extends keyof Settings>(group: K, value: Settings[K]) => {
    if (!latestDraft.current || !mounted.current) return
    latestDraft.current = { ...latestDraft.current, [group]: value }
    setDraft(latestDraft.current)
  }

  const saveProgress = async (progress: WizardProgress) => {
    if (saveInFlight.current || !baseline.current || !latestDraft.current) return
    if (stepId === 'settings' && !dictionaryPrepared) return
    const submitted = structuredClone(latestDraft.current)
    saveInFlight.current = true
    setSaving(true)
    try {
      const saved = await settings.saveWizardDraft(submitted, baseline.current, progress)
      if (!saved || !mounted.current) return
      const laterEdits = settingChanges(submitted, latestDraft.current)
      baseline.current = saved
      latestDraft.current = applySettingChanges(saved.settings, laterEdits)
      setDraft(latestDraft.current)
      // A picker can settle while a save is pending. Keep those new edits on
      // this step so a successful older request cannot silently discard them.
      if (laterEdits.length) return
      // Progress can itself conflict; navigate using the resolved saved value.
      if (progress.completed && saved.settings.onboarding.completed) onFinished()
      else setStep(onboardingStepIndex(saved.settings.onboarding.last_step))
    } finally {
      saveInFlight.current = false
      if (mounted.current) setSaving(false)
    }
  }

  const chooseDirectory = async (key: keyof Settings['directories']) => {
    try {
      const selected = await desktopClient.selectDirectory(currentDraft.directories[key])
      if (selected && latestDraft.current) updateDraft('directories', { ...latestDraft.current.directories, [key]: selected })
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason))
    }
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
        <fieldset className="onboarding-fields" disabled={saving}>
        {stepId === 'welcome' && <WelcomeStep />}
        {stepId === 'components' && <ComponentsStep capabilities={capabilities} checking={checking} busy={capabilityBusy} onReviewInstall={onReviewInstall} onLocateExisting={onLocateExisting} onCheckAgain={onCheckAgain} />}
        {stepId === 'settings' && <InitialSettingsStep draft={currentDraft} dictionary={dictionary} dictionaryPrepared={dictionaryPrepared} onDictionaryPrepared={() => setDictionaryPrepared(true)} onChange={updateDraft} onChooseDirectory={(key) => void chooseDirectory(key)} />}
        {stepId === 'add-media' && <AddMediaStep queue={queue} settings={currentDraft} onAdded={setFirstFileSource} />}
        {stepId === 'process-media' && <ProcessMediaStep source={firstFileSource} queue={queue} settings={currentDraft} capabilities={capabilities} />}
        {stepId === 'finish' && <FinishStep settings={currentDraft} capabilities={capabilities} dictionaryPrepared={dictionaryPrepared} />}
        </fieldset>
      </div>
      <footer className="onboarding-actions">
        <button className="button secondary" disabled={step === 0 || saving} onClick={() => setStep((current) => current - 1)}><ArrowLeft size={16} />Back</button>
        <span aria-live="polite">Step {step + 1} of {ONBOARDING_STEPS.length}: {ONBOARDING_STEPS[step].label}</span>
        {stepId === 'finish'
          ? <button className="button primary" disabled={saving} onClick={() => void saveProgress({ completed: true, last_step: 'finish' })}><ShieldCheck size={16} />Finish setup</button>
          : <button className="button primary" disabled={saving || (stepId === 'settings' && !dictionaryPrepared)} onClick={() => void saveProgress({ last_step: nextOnboardingStep(step) })}>Save & Continue<ArrowRight size={16} /></button>}
      </footer>
    </div>
  </section>
}

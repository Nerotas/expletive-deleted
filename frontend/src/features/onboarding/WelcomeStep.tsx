import { Check, FileAudio, ListChecks, ShieldCheck } from 'lucide-react'
import { OnboardingStepHeading } from './OnboardingStepHeading'

export function WelcomeStep() {
  return <>
    <OnboardingStepHeading title="Welcome to Expletive Deleted" subtitle="Set up private, reviewable media processing in a few clear steps." />
    <div className="onboarding-lead">
      <ShieldCheck size={34} />
      <div>
        <strong>Your media stays on this computer</strong>
        <p>Files and transcripts are processed locally. Your originals stay where they are unless you later choose to archive them after a verified censored copy is ready.</p>
      </div>
    </div>
    <div className="onboarding-summary">
      <SummaryItem icon={<ListChecks />} title="Prepare" detail="Check the components this computer needs." />
      <SummaryItem icon={<FileAudio />} title="Choose" detail="Pick your words, folders, and workflow." />
      <SummaryItem icon={<Check />} title="Try" detail="Add and process a first file now or later." />
    </div>
    <p className="onboarding-caution">Automatic speech recognition and censoring can miss things. Review the transcript and the finished file before sharing it.</p>
  </>
}

function SummaryItem({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) {
  return <article>{icon}<strong>{title}</strong><span>{detail}</span></article>
}

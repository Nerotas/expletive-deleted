import { useRef, useState } from 'react'
import { FilePlus2, Upload } from 'lucide-react'
import type { ImportResult, Settings } from '../../types/domain'
import type { QueueController } from '../queue/useQueue'
import { OnboardingStepHeading } from './OnboardingStepHeading'

type AddMediaStepProps = {
  queue: QueueController
  settings: Settings
  onAdded: (source: string) => void
}

export function AddMediaStep({ queue, settings, onAdded }: AddMediaStepProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [results, setResults] = useState<ImportResult[] | null>(null)

  const importFiles = async () => {
    if (!files.length) return
    const imported = await queue.importSources(files)
    setResults(imported)
    const firstAdded = imported.find((result) => result.status === 'added')
    if (firstAdded) onAdded(firstAdded.destination ?? firstAdded.source)
  }

  return <>
    <OnboardingStepHeading title="Add a first file" subtitle="You can try a file now, or finish setup and return to Queue later." />
    <div className="onboarding-lead"><FilePlus2 size={34} /><div><strong>Adding a file copies it to Ready</strong><p>Your original stays where it is. The app checks supported types and destination collisions before the copy; selecting a file does not start processing.</p></div></div>
    <section className="onboarding-import" aria-labelledby="onboarding-import-title" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); setFiles(Array.from(event.dataTransfer.files)); setResults(null) }}>
      <Upload size={28} /><h3 id="onboarding-import-title">Choose a file or drop it here</h3><p>Files will be copied to <code>{settings.directories.input}</code>.</p>
      <input ref={inputRef} className="visually-hidden" type="file" multiple accept="audio/*,video/*" aria-label="Choose media files to copy to Ready" onChange={(event) => { setFiles(Array.from(event.target.files ?? [])); setResults(null) }} />
      <button className="button secondary" type="button" onClick={() => inputRef.current?.click()}>Choose files</button>
    </section>
    {files.length > 0 && <section className="onboarding-import-confirmation" aria-live="polite"><strong>{files.length} {files.length === 1 ? 'file is' : 'files are'} ready to copy</strong><span>{files.map((file) => file.name).join(', ')}</span><button className="button primary" disabled={queue.busy} onClick={() => void importFiles()}>Copy to Ready</button></section>}
    {results && <p className="selection-confirmation">{results.some((result) => result.status === 'added') ? <><FilePlus2 size={15} />File added to Ready. You can create its transcript in the next step.</> : 'No files were added. Review the message above and try another supported file.'}</p>}
    <p className="onboarding-caution">Prefer to do this later? Continue without adding a file. Setup does not change the original media you already own.</p>
  </>
}

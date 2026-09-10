type ImportConfirmationCardProps = {
  fileCount: number
  fileNames: string
  busy: boolean
  onCopy: () => void
}

export function ImportConfirmationCard({ fileCount, fileNames, busy, onCopy }: ImportConfirmationCardProps) {
  return <section className="onboarding-import-confirmation" aria-live="polite">
    <strong>{fileCount} {fileCount === 1 ? 'file is' : 'files are'} ready to copy</strong>
    <span>{fileNames}</span>
    <button className="button primary" disabled={busy} onClick={onCopy}>Copy to Ready</button>
  </section>
}
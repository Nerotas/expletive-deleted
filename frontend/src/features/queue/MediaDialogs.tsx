import { Trash2 } from 'lucide-react'
import type { ImportResult } from '../../types/domain'
import { fileName } from '../../utils/format'

export type PurgeRequest = { source: string; label: string } | 'all' | null

export function CopyDialog({ files, copying, results, readyPath, onCancel, onConfirm }: { files: File[]; copying: boolean; results: ImportResult[] | null; readyPath?: string; onCancel: () => void; onConfirm: () => void }) {
  const added = results?.filter((result) => result.status === 'added').length ?? 0
  return <div className="modal-backdrop" role="presentation"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="copy-dialog-title">
    <p className="eyebrow">Add files</p>
    <h2 id="copy-dialog-title">{copying ? 'Copying to Ready' : results ? 'Copy complete' : `Add ${files.length} ${files.length === 1 ? 'file' : 'files'} to Ready?`}</h2>
    {!results ? <p>They will be copied to <strong>{readyPath}</strong>. Your originals stay in their current folders.</p> : <>
      <p>{added ? `${added} ${added === 1 ? 'file was' : 'files were'} added to Ready.` : 'No files were added to Ready.'}</p>
      <ul className="copy-results">{results.map((result) => <li key={result.source} className={result.status}>{fileName(result.source)} — {result.status === 'added' ? 'Added to Ready' : result.detail}</li>)}</ul>
    </>}
    <div className="modal-actions">{results ? <button className="button primary" onClick={onCancel}>Done</button> : <>
      <button className="button secondary" disabled={copying} onClick={onCancel}>Cancel</button>
      <button className="button primary" disabled={copying} onClick={onConfirm}>{copying ? 'Copying to Ready…' : 'Add to Ready'}</button>
    </>}</div>
  </section></div>
}

export function PurgeDialog({ request, busy, onCancel, onConfirm }: { request: Exclude<PurgeRequest, null>; busy: boolean; onCancel: () => void; onConfirm: () => void }) {
  const all = request === 'all'
  return <div className="modal-backdrop" role="presentation"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="purge-dialog-title">
    <p className="eyebrow">Permanent deletion</p>
    <h2 id="purge-dialog-title">{all ? 'Purge all archived originals?' : `Delete ${request.label}?`}</h2>
    <p>This permanently deletes {all ? 'every original in Processed' : 'this archived original'}. This cannot be undone.</p>
    <div className="modal-actions">
      <button className="button secondary" disabled={busy} onClick={onCancel}>Cancel</button>
      <button className="button danger" disabled={busy} onClick={onConfirm}><Trash2 size={16} />Delete permanently</button>
    </div>
  </section></div>
}

import { useEffect, useId, useRef, useState } from 'react'
import type { SettingsConflict, SettingsField } from '../../types/domain'
import { settingsFieldLabel } from './settings-transactions'
import './settings.css'

type Props = {
  revision?: string
  returnFocusTo?: HTMLElement | null
  conflicts: SettingsConflict[]
  busy: boolean
  verified?: boolean
  error?: string | null
  onCancel: () => void
  onResolve: (choices: Partial<Record<SettingsField, boolean>>) => void
}

export function SettingsConflictDialog({ revision, returnFocusTo, conflicts, busy, verified, error, onCancel, onResolve }: Props) {
  const title = useId()
  const panel = useRef<HTMLElement>(null)
  const conflictRevision = revision ?? JSON.stringify(conflicts)
  const [selection, setSelection] = useState<{ revision: string; choices: Partial<Record<SettingsField, boolean>> }>({ revision: conflictRevision, choices: {} })
  const choices = selection.revision === conflictRevision ? selection.choices : {}
  const cancel = useRef(onCancel)
  const pending = useRef(busy)
  useEffect(() => { cancel.current = onCancel; pending.current = busy }, [onCancel, busy])
  useEffect(() => {
    const previous = returnFocusTo ?? document.activeElement as HTMLElement | null
    panel.current?.focus()
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending.current) { event.preventDefault(); cancel.current() }
      if (event.key !== 'Tab') return
      const elements = [...(panel.current?.querySelectorAll<HTMLElement>(':is(button, input):not(:disabled)') ?? [])]
      if (!elements.length) { event.preventDefault(); panel.current?.focus(); return }
      const first = elements[0], last = elements.at(-1)
      if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) {
        event.preventDefault(); last?.focus()
      } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === panel.current)) {
        event.preventDefault(); first?.focus()
      }
    }
    document.addEventListener('keydown', keydown)
    return () => {
      document.removeEventListener('keydown', keydown)
      previous?.focus()
      // The wizard re-enables its Save button after the controller's promise
      // settles. Wait for that commit if the immediate restoration was blocked.
      if (previous?.matches(':disabled')) requestAnimationFrame(() => {
        if (previous.isConnected && document.activeElement === document.body) previous.focus()
      })
    }
  }, [returnFocusTo])
  // Refresh choices without remounting the dialog: repeated conflicts must keep
  // the original focus-restoration target, even after their revision changes.
  useEffect(() => { panel.current?.focus() }, [conflictRevision])

  const choose = (field: SettingsField, value: boolean) => {
    // A verified FFmpeg/FFprobe installation is selected as a pair.
    const pair = verified && ['runtime.ffmpeg_path', 'runtime.ffprobe_path'].includes(field)
    setSelection({ revision: conflictRevision, choices: { ...choices, [field]: value,
      ...(pair ? { 'runtime.ffmpeg_path': value, 'runtime.ffprobe_path': value } : {}) } })
  }
  return <div className="modal-backdrop">
    <section ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby={title} className="modal settings-conflict">
      <h2 id={title}>{verified ? 'Review component settings' : 'Settings changed elsewhere'}</h2>
      <p>{verified ? 'Completed downloads are retained. Choose which paths to keep; applying your choices does not reinstall components.' : 'Choose which values to save. Your other edits are retained.'}</p>
      {error && <p role="alert">{error}</p>}
      {conflicts.map((conflict) => <fieldset key={conflict.field} disabled={busy}>
        <legend>{settingsFieldLabel(conflict.field)}</legend>
        <label><input type="radio" name={`${title}-${conflict.field}`} checked={choices[conflict.field] === false} onChange={() => choose(conflict.field, false)} />Keep current: <span>{String(conflict.current ?? 'Not set')}</span></label>
        <label><input type="radio" name={`${title}-${conflict.field}`} checked={choices[conflict.field] === true} onChange={() => choose(conflict.field, true)} />{verified ? 'Use verified' : 'Use my edit'}: <span>{String(conflict.proposed ?? 'Not set')}</span></label>
      </fieldset>)}
      <div className="modal-actions">
        <button className="button secondary" disabled={busy} onClick={onCancel}>Cancel</button>
        <button className="button primary" disabled={busy || conflicts.some(({ field }) => choices[field] === undefined)} onClick={() => onResolve(choices)}>Apply choices</button>
      </div>
    </section>
  </div>
}

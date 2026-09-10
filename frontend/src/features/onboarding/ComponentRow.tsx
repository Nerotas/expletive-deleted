import { Check } from 'lucide-react'

type ComponentRowProps = {
  title: string
  detail: string
  ready: boolean
  checking: boolean
  busy: boolean
  onLocate?: () => void
  onGet?: () => void
  optional?: boolean
}

export function ComponentRow({ title, detail, ready, checking, busy, onLocate, onGet, optional = false }: ComponentRowProps) {
  const state = checking ? 'Checking' : ready ? 'Verified' : optional ? 'Not downloaded' : 'Needs attention'

  return <article className="component-row">
    <span className={ready ? 'ready' : optional ? 'informational' : undefined}>{ready ? <Check size={16} /> : optional ? 'i' : '!'}</span>
    <div><strong>{title}</strong><small>{detail}</small></div>
    <b>{state}</b>
    {!ready && <div className="component-actions">
      {onLocate && <button className="button secondary" disabled={busy} onClick={onLocate}>Locate existing</button>}
      {onGet && <button className="button primary" disabled={busy} onClick={onGet}>Download model</button>}
    </div>}
  </article>
}
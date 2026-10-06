import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { ChevronDown, X } from 'lucide-react'
import type { SystemCheck } from '../../types/domain'
import { SystemCheckStatus } from './SystemCheckStatus'

type Props = {
  children: ReactNode
  className: string
  checking: boolean
  state?: SystemCheck | null
  error: string | null
  onRetry: () => void
}

export function SystemCheckPopover({ children, className, checking, state, error, onRetry }: Props) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)
  const close = () => { setOpen(false); trigger.current?.focus() }

  useEffect(() => {
    if (!open) return
    closeButton.current?.focus()
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setOpen(false); trigger.current?.focus() }
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  return <div className="system-check-anchor" ref={root}>
    <button className={className} type="button" ref={trigger} aria-haspopup="dialog" aria-expanded={open} aria-controls={id} onClick={() => setOpen((current) => !current)}>{children}<ChevronDown size={14} /></button>
    {open && <div className="system-check-popover" id={id} role="dialog" aria-label="System verification">
      <div className="system-check-popover-heading">
        <strong>System verification</strong>
        <button className="icon-button" type="button" ref={closeButton} aria-label="Close system verification" onClick={close}><X size={16} /></button>
      </div>
      <SystemCheckStatus checking={checking} state={state} error={error} onRetry={onRetry} />
    </div>}
  </div>
}

import { AlertCircle, Check } from 'lucide-react'

type AlertBannerProps = {
  tone: 'error' | 'success'
  message: string
  onDismiss: () => void
}

export function AlertBanner({ tone, message, onDismiss }: AlertBannerProps) {
  return (
    <div className={`alert ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      {tone === 'error' ? <AlertCircle size={18} /> : <Check size={18} />}
      <span>{message}</span>
      <button type="button" onClick={onDismiss}>Dismiss</button>
    </div>
  )
}


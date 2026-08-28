import { LoaderCircle } from 'lucide-react'

export function LoadingRow({ children }: { children: string }) {
  return (
    <div className="loading-row">
      <LoaderCircle className="spin" size={20} />
      {children}
    </div>
  )
}


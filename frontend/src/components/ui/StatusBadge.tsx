import { LoaderCircle } from 'lucide-react'
import type { JobStatus, LibraryStatus } from '../../types/domain'
import { statusLabel } from '../../utils/format'

const ACTIVE_STATUSES: ReadonlyArray<JobStatus> = ['copying', 'transcribing', 'censoring', 'verifying']

export function StatusBadge({ status, label }: { status: LibraryStatus | JobStatus; label?: string }) {
  return (
    <span className={`status-badge status-${status}`}>
      {ACTIVE_STATUSES.includes(status as JobStatus) && (
        <LoaderCircle className="spin" size={13} />
      )}
      {label ?? statusLabel(status)}
    </span>
  )
}


import { LoaderCircle } from 'lucide-react'
import type { JobStatus, LibraryStatus } from '../../types/domain'
import { statusLabel } from '../../utils/format'

const ACTIVE_STATUSES: ReadonlyArray<JobStatus> = ['copying', 'transcribing', 'censoring', 'verifying']

export function StatusBadge({ status }: { status: LibraryStatus | JobStatus }) {
  return (
    <span className={`status-badge status-${status}`}>
      {ACTIVE_STATUSES.includes(status as JobStatus) && (
        <LoaderCircle className="spin" size={13} />
      )}
      {statusLabel(status)}
    </span>
  )
}


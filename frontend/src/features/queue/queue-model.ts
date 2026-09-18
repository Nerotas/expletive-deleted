import type { Job, LibraryItem } from '../../types/domain'
import { fileName } from '../../utils/format'

export type QueueRowModel = { item: LibraryItem; job?: Job; pendingJob?: Job }
export type QueueFilter = 'all' | 'ready' | 'queued' | 'transcribed' | 'finished'
export type QueueCategory = Exclude<QueueFilter, 'all'> | 'active' | 'other'
export type QueueSort = 'queue' | 'name' | 'dateAdded' | 'status'
export type SortDirection = 'ascending' | 'descending'

export const TERMINAL_STATUSES = new Set<Job['status']>(['completed', 'failed', 'cancelled', 'transcribed'])
export const RUNNING_STATUSES = new Set<Job['status']>(['copying', 'transcribing', 'censoring', 'verifying', 'downloading', 'preparing'])

export function isBulkSelectable(item: LibraryItem, job?: Job, pendingJob?: Job) {
  return job?.source_type !== 'youtube' && !pendingJob && (item.status === 'ready' || item.status === 'transcribed')
}

export function buildQueueRows(library: LibraryItem[], jobs: Job[], copyJobDates: Record<string, string>): QueueRowModel[] {
  // A pending job takes precedence over historical results for the same source.
  const mergedRows: QueueRowModel[] = library.map((item) => {
    const sourceJobs = jobs.filter((candidate) => candidate.source === item.source)
    return {
      item,
      job: sourceJobs.at(-1),
      pendingJob: sourceJobs.find((candidate) => !TERMINAL_STATUSES.has(candidate.status)),
    }
  })
  const copyJobs = jobs
    .filter((job) => job.source_type !== 'youtube' && job.mode === 'copy' && !TERMINAL_STATUSES.has(job.status))
    .filter((job) => !library.some((item) => item.source === job.source))
  const copyRows = copyJobs
    .map((job): QueueRowModel => ({
      item: {
        source: job.source,
        status: 'ready',
        date_added: copyJobDates[job.id] ?? '',
        transcript: null,
        output: null,
      },
      job,
      pendingJob: job,
    }))
  mergedRows.push(...copyRows)
  mergedRows.push(...jobs.filter((job) => job.source_type === 'youtube' && job.status !== 'completed').map((job): QueueRowModel => ({
    item: { source: job.source, status: 'ready', date_added: '', transcript: null, output: null },
    job,
    pendingJob: TERMINAL_STATUSES.has(job.status) ? undefined : job,
  })))
  return mergedRows
}

export function selectQueueRows(
  mergedRows: QueueRowModel[], queuedJobs: Job[], filter: QueueFilter,
  sort: QueueSort, sortDirection: SortDirection, selectedSources: Set<string>,
) {
  // Keep running jobs visible above every filter; bulk submission follows table order.
  const queuedPositions = new Map(queuedJobs.map((job, index) => [job.id, index + 1]))
  const rows = mergedRows.map((row) => {
    const active = Boolean(row.pendingJob && RUNNING_STATUSES.has(row.pendingJob.status))
    const queuePosition = row.pendingJob ? queuedPositions.get(row.pendingJob.id) : undefined
    const category: QueueCategory = active
      ? 'active'
      : queuePosition != null
        ? 'queued'
        : row.item.status === 'ready'
          ? 'ready'
          : row.item.status === 'transcribed'
            ? 'transcribed'
            : row.item.status === 'finished'
              ? 'finished'
              : 'other'
    return { ...row, active, queuePosition, category }
  })
  const categoryOrder = ['active', 'queued', 'ready', 'transcribed', 'finished', 'other']
  const sortedRows = [...rows].sort((left, right) => {
    const nameComparison = fileName(left.item.source).localeCompare(fileName(right.item.source), undefined, { numeric: true, sensitivity: 'base' })
    let comparison: number
    if (sort === 'name') comparison = nameComparison
    else if (sort === 'dateAdded') comparison = new Date(left.item.date_added).getTime() - new Date(right.item.date_added).getTime() || nameComparison
    else if (sort === 'status') {
      comparison = categoryOrder.indexOf(left.category) - categoryOrder.indexOf(right.category) || nameComparison
    } else {
      const leftRank = left.active ? 0 : left.queuePosition != null ? 1 : 2
      const rightRank = right.active ? 0 : right.queuePosition != null ? 1 : 2
      comparison = leftRank - rightRank
        || (left.queuePosition ?? Number.MAX_SAFE_INTEGER) - (right.queuePosition ?? Number.MAX_SAFE_INTEGER)
        || nameComparison
    }
    return sortDirection === 'ascending' ? comparison : -comparison
  })
  const activeRows = rows.filter((row) => row.active)
  const visibleRows = sortedRows.filter((row) => !row.active && (filter === 'all' || row.category === filter))
  const visibleSelectable = visibleRows
    .filter(({ item, job, pendingJob }) => isBulkSelectable(item, job, pendingJob))
    .map(({ item }) => item.source)
  const orderedSelection = sortedRows
    .map(({ item }) => item.source)
    .filter((source) => selectedSources.has(source))
  const counts = {
    all: rows.length,
    ready: rows.filter((row) => row.category === 'ready').length,
    queued: rows.filter((row) => row.category === 'queued').length,
    active: rows.filter((row) => row.category === 'active').length,
    transcribed: rows.filter((row) => row.category === 'transcribed').length,
    finished: rows.filter((row) => row.category === 'finished').length,
  }
  return { rows, activeRows, visibleRows, visibleSelectable, orderedSelection, counts }
}

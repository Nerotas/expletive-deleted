import { describe, expect, it } from 'vitest'
import type { Job, LibraryItem } from '../../types/domain'
import { buildQueueRows, isBulkSelectable, selectQueueRows } from './queue-model'

const item = (source: string, status: LibraryItem['status'] = 'ready'): LibraryItem => ({
  source, status, date_added: '2026-09-16T12:00:00Z', transcript: null, output: null, duration_seconds: null,
})
const job = (id: string, source: string, status: Job['status'], extra: Partial<Job> = {}): Job => ({
  id, source, status, mode: 'report_only', progress_percent: null, error: null, ...extra,
})

describe('queue row projection', () => {
  it('retains a pending action even when later history contains a terminal job', () => {
    const pending = job('pending', 'movie.mp4', 'queued')
    const previous = job('previous', 'movie.mp4', 'completed')
    const [row] = buildQueueRows([item('movie.mp4', 'finished')], [pending, previous], {})
    expect(row.pendingJob).toBe(pending)
    expect(row.job).toBe(previous)
    expect(isBulkSelectable(row.item, row.job, row.pendingJob)).toBe(false)
  })

  it('shows active copies before discovery without duplicating discovered media', () => {
    const copying = job('copy', 'new.mp4', 'copying', { mode: 'copy' })
    const timestamp = '2026-09-16T12:30:00Z'
    const [row] = buildQueueRows([], [copying], { copy: timestamp })
    expect(row.item.date_added).toBe(timestamp)
    expect(row.pendingJob).toBe(copying)
    expect(buildQueueRows([item('new.mp4')], [copying], {})).toHaveLength(1)
    expect(buildQueueRows([], [{ ...copying, status: 'completed' }], {})).toEqual([])
  })

  it('keeps failed downloads for retry and excludes completed downloads and remote bulk selection', () => {
    const failed = job('failed', 'https://youtu.be/failed', 'failed', { source_type: 'youtube' })
    const completed = job('completed', 'https://youtu.be/completed', 'completed', { source_type: 'youtube' })
    const [row] = buildQueueRows([], [failed, completed], {})
    expect(row.job).toBe(failed)
    expect(row.pendingJob).toBeUndefined()
    expect(isBulkSelectable(row.item, row.job, row.pendingJob)).toBe(false)
    expect(buildQueueRows([], [failed, completed], {})).toHaveLength(1)
  })

  it('keeps running jobs above filters and submits selected files in the displayed sort order', () => {
    const library = [item('clip10.mp4'), item('clip2.mp4'), item('active.mp4'), item('waiting.mp4')]
    const jobs = [job('active', 'active.mp4', 'transcribing'), job('waiting', 'waiting.mp4', 'queued')]
    const rows = buildQueueRows(library, jobs, {})
    const selected = new Set(['clip10.mp4', 'clip2.mp4'])
    const result = selectQueueRows(rows, [jobs[1]], 'ready', 'name', 'ascending', selected)
    expect(result.activeRows.map((row) => row.item.source)).toEqual(['active.mp4'])
    expect(result.visibleSelectable).toEqual(['clip2.mp4', 'clip10.mp4'])
    expect(result.orderedSelection).toEqual(['clip2.mp4', 'clip10.mp4'])
    expect(result.counts).toEqual({ all: 4, ready: 2, queued: 1, active: 1, transcribed: 0, finished: 0 })
    expect(selectQueueRows(rows, [jobs[1]], 'ready', 'name', 'descending', selected).orderedSelection)
      .toEqual(['clip10.mp4', 'clip2.mp4'])
    expect(library.map((entry) => entry.source)).toEqual(['clip10.mp4', 'clip2.mp4', 'active.mp4', 'waiting.mp4'])
  })

  it('uses backend queue position instead of file name for waiting jobs', () => {
    const jobs = [job('z', 'z.mp4', 'queued'), job('a', 'a.mp4', 'queued')]
    const rows = buildQueueRows([item('a.mp4'), item('z.mp4')], jobs, {})
    const result = selectQueueRows(rows, jobs, 'queued', 'queue', 'ascending', new Set())
    expect(result.visibleRows.map((row) => [row.item.source, row.queuePosition]))
      .toEqual([['z.mp4', 1], ['a.mp4', 2]])
  })
})

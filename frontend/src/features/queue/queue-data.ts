import type { DesktopClient } from '../../services/desktop-client'
import type { JobEvent } from '../../types/domain'
import { TERMINAL_STATUSES } from './queue-model'

export async function loadQueue(client: DesktopClient, copyJobDates: Map<string, string>) {
  // Poll only queue resources; settings refreshes must never replace an unsaved draft.
  const [library, archive, localJobs, downloads] = await Promise.all([client.listLibrary(), client.listArchive(), client.listJobs(), client.listDownloads()])
  const jobs = [...localJobs, ...downloads]
  const eventGroups = await Promise.all(jobs.map((job) => job.source_type === 'youtube' ? client.listDownloadEvents(job.id) : client.listJobEvents(job.id)))
  const jobEvents: Record<string, JobEvent> = Object.fromEntries(
    eventGroups.flatMap((events) =>
      events.length ? [[events.at(-1)!.job_id, events.at(-1)!]] : [],
    ),
  )
  // Copy jobs have no library timestamp yet. Retain their first-seen date across polls.
  const activeCopyJobIds = new Set(
    jobs
      .filter((job) => job.mode === 'copy' && !TERMINAL_STATUSES.has(job.status))
      .map((job) => job.id),
  )
  for (const jobId of copyJobDates.keys()) {
    if (!activeCopyJobIds.has(jobId)) copyJobDates.delete(jobId)
  }
  for (const jobId of activeCopyJobIds) {
    copyJobDates.set(jobId, copyJobDates.get(jobId) ?? new Date().toISOString())
  }
  return { library, archive, jobs, jobEvents, copyJobDates: Object.fromEntries(copyJobDates) }
}

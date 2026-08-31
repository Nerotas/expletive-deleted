import { useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { desktopClient, type DesktopClient } from '../../services/desktop-client'
import type { ArchiveItem, ImportResult, Job, JobEvent, JobSubmissionResult } from '../../types/domain'
import { errorMessage, fileName } from '../../utils/format'

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled', 'transcribed'])
const RUNNING_STATUSES = new Set(['transcribing', 'censoring', 'verifying'])

type QueueOptions = {
  client?: DesktopClient
  onError: (message: string) => void
  onNotice: (message: string) => void
  pollInterval?: number
}

async function loadQueue(client: DesktopClient) {
  const [library, archive, jobs] = await Promise.all([client.listLibrary(), client.listArchive(), client.listJobs()])
  const eventGroups = await Promise.all(jobs.map((job) => client.listJobEvents(job.id)))
  const jobEvents: Record<string, JobEvent> = Object.fromEntries(
    eventGroups.flatMap((events) =>
      events.length ? [[events.at(-1)!.job_id, events.at(-1)!]] : [],
    ),
  )
  return { library, archive, jobs, jobEvents }
}

export function useQueue({
  client = desktopClient,
  onError,
  onNotice,
  pollInterval = 1_500,
}: QueueOptions) {
  const query = useQuery({
    queryKey: ['queue'],
    queryFn: () => loadQueue(client),
    refetchInterval: pollInterval,
  })

  useEffect(() => {
    if (query.error) onError(errorMessage(query.error))
  }, [onError, query.error])

  const actionMutation = useMutation<unknown, unknown, () => Promise<unknown>>({
    mutationFn: (action) => action(),
    onSuccess: async () => { await query.refetch() },
    onError: (reason) => onError(errorMessage(reason)),
  })
  const library = query.data?.library ?? []
  const jobs = query.data?.jobs ?? []
  const archive: ArchiveItem[] = query.data?.archive ?? []
  const runningJob = jobs.find((job) => RUNNING_STATUSES.has(job.status))
  const queuedJobs = jobs.filter((job) => job.status === 'queued')
  const nonTerminalJobs = jobs.filter((job) => !TERMINAL_STATUSES.has(job.status))
  const run = async <T>(action: () => Promise<T>): Promise<T | undefined> => {
    return actionMutation.mutateAsync(action).catch(() => undefined) as Promise<T | undefined>
  }

  return {
    library,
    jobs,
    jobEvents: query.data?.jobEvents ?? {},
    runningJob,
    queuedJobs,
    queueIdle: nonTerminalJobs.length === 0,
    loading: query.isLoading,
    busy: actionMutation.isPending,
    refresh: async () => { await query.refetch() },
    submitFile: (source: string, mode: Job['mode']) => run(async () => {
      await client.submitJob(source, mode)
      onNotice(`${fileName(source)} queued`)
    }).then(() => undefined),
    submitFiles: async (sources: string[], mode: Job['mode']): Promise<JobSubmissionResult[]> => {
      const results = await run(() => client.submitJobs(sources, mode))
      if (!results) return []
      const queued = results.filter((result) => result.status === 'queued').length
      const rejected = results.filter((result) => result.status === 'rejected')
      if (rejected.length) {
        onError(
          `${queued} queued; ${rejected.length} could not be queued. ${rejected[0].detail}`,
        )
      } else {
        onNotice(`${queued} ${queued === 1 ? 'file' : 'files'} queued`)
      }
      return results
    },
    cancelActive: () => runningJob ? run(async () => {
      await client.cancelJob(runningJob.id)
      onNotice('Cancellation requested')
    }) : Promise.resolve(),
    removeQueued: (job: Job) => run(async () => {
      await client.cancelJob(job.id)
      onNotice(`${fileName(job.source)} removed from the queue`)
    }).then(() => undefined),
    retryJob: (job: Job) => run(async () => {
      await client.submitJob(job.source, job.mode)
      onNotice(`${fileName(job.source)} queued again`)
    }),
    archiveSource: (source: string) => run(async () => {
      await client.archiveSource(source)
      onNotice(`${fileName(source)} moved to Processed`)
    }),
    importSources: async (files: File[]): Promise<ImportResult[]> => {
      const sources = files.map((file) => client.getDroppedFilePath(file)).filter(Boolean)
      if (!sources.length) return []
      const results = await client.importSources(sources).catch((reason) => {
        onError(errorMessage(reason))
        return [] as ImportResult[]
      })
      await query.refetch()
      if (results.length) {
        const added = results.filter((result) => result.status === 'added').length
        onNotice(added ? `${added} ${added === 1 ? 'file' : 'files'} added to Ready` : 'No files were added to Ready')
      }
      return results
    },
    archive,
    purgeArchiveSource: (source: string) => run(async () => {
      await client.purgeArchiveSource(source)
      onNotice(`${fileName(source)} permanently deleted`)
    }),
    purgeArchive: () => run(async () => {
      await client.purgeArchive()
      onNotice('Archived originals permanently deleted')
    }),
  }
}

export type QueueController = ReturnType<typeof useQueue>

import { useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { desktopClient, type DesktopClient } from '../../services/desktop-client'
import type { Job, JobEvent, Settings } from '../../types/domain'
import { errorMessage, fileName } from '../../utils/format'

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled', 'transcribed'])

type QueueOptions = {
  client?: DesktopClient
  onError: (message: string) => void
  onNotice: (message: string) => void
  pollInterval?: number
}

async function loadQueue(client: DesktopClient) {
  const [library, jobs] = await Promise.all([client.listLibrary(), client.listJobs()])
  const eventGroups = await Promise.all(jobs.map((job) => client.listJobEvents(job.id)))
  const jobEvents: Record<string, JobEvent> = Object.fromEntries(
    eventGroups.flatMap((events) =>
      events.length ? [[events.at(-1)!.job_id, events.at(-1)!]] : [],
    ),
  )
  return { library, jobs, jobEvents }
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

  const actionMutation = useMutation({
    mutationFn: (action: () => Promise<void>) => action(),
    onSuccess: async () => { await query.refetch() },
    onError: (reason) => onError(errorMessage(reason)),
  })
  const library = query.data?.library ?? []
  const jobs = query.data?.jobs ?? []
  const activeJob = jobs.find((job) => !TERMINAL_STATUSES.has(job.status))
  const run = async (action: () => Promise<void>) => {
    await actionMutation.mutateAsync(action).catch(() => undefined)
  }

  return {
    library,
    jobs,
    jobEvents: query.data?.jobEvents ?? {},
    activeJob,
    loading: query.isLoading,
    busy: actionMutation.isPending,
    refresh: async () => { await query.refetch() },
    startBatch: (mode: Settings['processing']['mode']) => run(async () => {
      const pending = library.filter((item) => item.status !== 'finished')
      for (const item of pending) await client.submitJob(item.source, mode)
      onNotice(`${pending.length} ${pending.length === 1 ? 'file' : 'files'} queued`)
    }),
    cancelActive: () => activeJob ? run(async () => {
      await client.cancelJob(activeJob.id)
      onNotice('Cancellation requested')
    }) : Promise.resolve(),
    retryJob: (job: Job) => run(async () => {
      await client.submitJob(job.source, job.mode)
      onNotice(`${fileName(job.source)} queued again`)
    }),
    archiveSource: (source: string) => run(async () => {
      await client.archiveSource(source)
      onNotice(`${fileName(source)} moved to Processed`)
    }),
  }
}

export type QueueController = ReturnType<typeof useQueue>

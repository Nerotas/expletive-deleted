import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { desktopClient, type DesktopClient } from '../../services/desktop-client'
import type { ArchiveItem, ImportResult, Job, JobSubmissionOptions, JobSubmissionResult } from '../../types/domain'
import { errorMessage, fileName } from '../../utils/format'

import { RUNNING_STATUSES, TERMINAL_STATUSES } from './queue-model'
import { loadQueue } from './queue-data'

type QueueOptions = {
  client?: DesktopClient
  enabled?: boolean
  onError: (message: string) => void
  onNotice: (message: string) => void
  pollInterval?: number
}

export type YoutubeSubmitResult = 'success' | 'authentication_required' | 'browser_cookies_unavailable' | 'failed'
export type YoutubeSubmitOutcome = { status: YoutubeSubmitResult; diagnostic?: string }

function isAuthenticationRequired(reason: unknown): boolean {
  if (typeof reason !== 'object' || reason === null) return false
  const error = reason as { code?: unknown; message?: unknown }
  return error.code === 'authentication_required'
    || error.message === 'YouTube requires authentication or verification'
}

function isBrowserCookiesUnavailable(reason: unknown): boolean {
  return typeof reason === 'object' && reason !== null
    && (reason as { code?: unknown }).code === 'browser_cookies_unavailable'
}

function diagnosticOf(reason: unknown): string | undefined {
  if (typeof reason !== 'object' || reason === null) return undefined
  const diagnostic = (reason as { diagnostic?: unknown }).diagnostic
  return typeof diagnostic === 'string' ? diagnostic : undefined
}

export function useQueue({
  client = desktopClient,
  enabled = true,
  onError,
  onNotice,
  pollInterval = 1_500,
}: QueueOptions) {
  const queryClient = useQueryClient()
  const copyJobDates = useRef(new Map<string, string>())
  const checkedFailures = useRef(new Set<string>())
  const query = useQuery({
    queryKey: ['queue'],
    queryFn: () => loadQueue(client, copyJobDates.current),
    enabled,
    refetchInterval: enabled ? pollInterval : false,
  })

  useEffect(() => {
    if (query.error) onError(errorMessage(query.error))
  }, [onError, query.error])

  useEffect(() => {
    let needsCheck = false
    for (const job of query.data?.jobs ?? []) {
      if (job.status !== 'failed' || job.error?.code !== 'processing_failed' || checkedFailures.current.has(job.id)) continue
      checkedFailures.current.add(job.id)
      needsCheck = true
    }
    // Processing errors can hide a missing runtime component; check once per failed job.
    if (needsCheck) void queryClient.invalidateQueries({ queryKey: ['capabilities'] })
  }, [query.data, queryClient])

  const actionMutation = useMutation<unknown, unknown, () => Promise<unknown>>({
    mutationFn: (action) => action(),
    onSuccess: async () => { await query.refetch() },
    onError: (reason) => {
      if (!isAuthenticationRequired(reason) && !isBrowserCookiesUnavailable(reason)) onError(errorMessage(reason))
    },
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
    copyJobDates: query.data?.copyJobDates ?? {},
    runningJob,
    queuedJobs,
    queueIdle: nonTerminalJobs.length === 0,
    loading: query.isLoading,
    busy: actionMutation.isPending,
    refresh: async () => { await query.refetch() },
    openTranscodeFolder: () => run(() => client.openTranscodeFolder()).then(() => undefined),
    openExternal: (url: string) => run(() => client.openExternal(url)).then(() => undefined),
    openFile: (filePath: string) => run(() => client.openFile(filePath)).then(() => undefined),
    submitFile: (source: string, mode: Job['mode'], options?: JobSubmissionOptions) => run(async () => {
      if (options) await client.submitJob(source, mode, options)
      else await client.submitJob(source, mode)
      onNotice(`${fileName(source)} queued`)
    }).then(() => undefined),
    submitYoutubeDownload: async (url: string, retryId?: string, cookieBrowser?: string): Promise<YoutubeSubmitOutcome> => {
      try {
        await actionMutation.mutateAsync(() => client.submitYoutubeDownload(url, retryId, cookieBrowser))
        onNotice(retryId ? 'YouTube download queued again' : 'YouTube download queued')
        return { status: 'success' }
      } catch (reason) {
        const diagnostic = diagnosticOf(reason)
        if (isBrowserCookiesUnavailable(reason)) return { status: 'browser_cookies_unavailable', diagnostic }
        return { status: isAuthenticationRequired(reason) ? 'authentication_required' : 'failed', diagnostic }
      }
    },
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
      if (runningJob.source_type === 'youtube') await client.cancelDownload(runningJob.id)
      else await client.cancelJob(runningJob.id)
      onNotice('Cancellation requested')
    }) : Promise.resolve(),
    cancelJob: (job: Job) => run(async () => {
      if (job.source_type === 'youtube') await client.cancelDownload(job.id)
      else await client.cancelJob(job.id)
      onNotice('Cancellation requested')
    }),
    removeQueued: (job: Job) => run(async () => {
      if (job.source_type === 'youtube') await client.cancelDownload(job.id)
      else await client.cancelJob(job.id)
      onNotice(`${fileName(job.source)} removed from the queue`)
    }).then(() => undefined),
    retryJob: (job: Job) => run(async () => {
      if (job.source_type === 'youtube') {
        await client.submitYoutubeDownload(job.url ?? job.source, job.id, job.cookie_browser ?? undefined)
        onNotice('YouTube download queued again')
        return
      }
      const options: JobSubmissionOptions = {
        ...(job.force_transcribe ? { force_transcribe: true } : {}),
        ...(job.overwrite_output ? { overwrite_output: true } : {}),
      }
      if (Object.keys(options).length) await client.submitJob(job.source, job.mode, options)
      else await client.submitJob(job.source, job.mode)
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
    restoreArchiveSource: (source: string) => run(async () => {
      await client.restoreArchiveSource(source)
      onNotice(`${fileName(source)} returned to Ready`)
    }),
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

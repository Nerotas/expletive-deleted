import { unwrapInvokeResponse } from '../../shared/ipc-response'
import { decodeInstallStatus } from './install-status'
import type {
  Capabilities,
  ArchiveItem,
  DictionaryAction,
  DictionaryEntryPage,
  DictionaryInfo,
  DictionarySort,
  DictionaryMutationResult,
  DictionaryTarget,
  DiscoveredWords,
  InstallPlan,
  InstallStatus,
  ImportResult,
  Job,
  JobEvent,
  JobSubmissionResult,
  JobSubmissionOptions,
  LibraryItem,
  ReviewResult,
  Settings,
  SettingsSnapshot,
  SettingsResult,
  FieldChange,
  SettingsField,
} from '../types/domain'

// Keep preload access and wire method names here; features consume typed operations only.
function bridge() {
  if (!window.expletiveDeleted) {
    throw new Error('The Electron preload bridge did not load. Restart the desktop application.')
  }
  return window.expletiveDeleted
}

async function invoke<T>(method: string, params?: Record<string, unknown>, options?: import('../../shared/bridge').RequestOptions): Promise<T> {
  return unwrapInvokeResponse(await bridge().request<T>(method, params, options))
}

export const desktopClient = {
  getAppInfo: () => bridge().getAppInfo(),
  getBackendState: () => bridge().getBackendState(),
  onBackendState: (listener: (state: import('../../shared/bridge').BackendState) => void) => bridge().onBackendState(listener),
  restart: () => bridge().restart(),
  getSettings: () => invoke<SettingsSnapshot>('settings.get'),
  updateSettings: (settings: Settings, base: SettingsSnapshot) => invoke<SettingsResult>('settings.update', { settings, base }),
  patchSettings: (revision: string, changes: FieldChange[], strict = false) => invoke<SettingsResult>('settings.patch', { revision, changes, strict }),
  getCapabilities: () => invoke<Capabilities>('capabilities.get'),
  getDictionaryInfo: () => invoke<DictionaryInfo>('dictionary.info'),
  getDictionaryExclusions: (
    page: number,
    pageSize: number,
    sort: DictionarySort,
    direction: 'asc' | 'desc',
    search: string,
  ) => invoke<DictionaryEntryPage>('dictionary.exclusions', {
    page, page_size: pageSize, sort, direction, search,
  }),
  getCensoredWords: (
    page: number,
    pageSize: number,
    sort: DictionarySort,
    direction: 'asc' | 'desc',
    search: string,
  ) => invoke<DictionaryEntryPage>('dictionary.censored', {
    page, page_size: pageSize, sort, direction, search,
  }),
  getDiscoveredWords: () => invoke<DiscoveredWords>('dictionary.discovered'),
  updateDictionary: (action: DictionaryAction, target: DictionaryTarget, word: string) =>
    invoke<DictionaryMutationResult>(`dictionary.${action}`, { target, word }),
  restoreDictionaryDefaults: () => invoke<DictionaryMutationResult>('dictionary.restore_defaults'),
  importDictionary: () => bridge().importDictionary(),
  exportDictionary: () => bridge().exportDictionary(),
  getReview: (source: string) => invoke<ReviewResult>('reviews.list', { source }),
  planDependencies: (components: string[]) =>
    invoke<InstallPlan>('dependencies.plan', { components }),
  installDependencies: (planId: string) =>
    invoke<unknown>('dependencies.install', { plan_id: planId }).then((result) => decodeInstallStatus(result)),
  getInstallStatus: (installId: string, timeoutMs = 2000, generation?: number) =>
    invoke<InstallStatus>('dependencies.status', { install_id: installId }, { timeoutMs, generation }),
  getActiveInstall: (planId: string, timeoutMs = 2000, generation?: number) =>
    invoke<InstallStatus | null>('dependencies.active', { plan_id: planId }, { timeoutMs, generation }),
  cancelInstall: (installId: string) =>
    invoke<unknown>('dependencies.cancel', { install_id: installId }).then((result) => decodeInstallStatus(result, installId)),
  resolveInstallConflict: (installId: string, revision: string, choices: Partial<Record<SettingsField, 'keep_current' | 'use_verified'>>) =>
    invoke<unknown>('dependencies.resolve_conflict', { install_id: installId, revision, choices }).then((result) => decodeInstallStatus(result, installId)),
  inspectExistingFfmpeg: (path: string) =>
    invoke<{ ffmpeg_path: string; ffprobe_path: string; version: string | null }>(
      'dependencies.inspect_ffmpeg',
      { path },
    ),
  locateExistingFfmpeg: (path: string) =>
    invoke<InstallStatus>('dependencies.locate_ffmpeg', { path }),
  locateExistingModel: (path: string) =>
    invoke<InstallStatus>('dependencies.locate_model', { path }),
  locateExistingYtdlp: (path: string) =>
    invoke<InstallStatus>('dependencies.locate_ytdlp', { path }),
  listLibrary: () => invoke<LibraryItem[]>('library.list'),
  archiveSource: (source: string) => invoke<unknown>('library.archive', { source }),
  importSources: (sources: string[]) => invoke<ImportResult[]>('library.import', { sources }),
  listArchive: () => invoke<ArchiveItem[]>('archive.list'),
  restoreArchiveSource: (source: string) => invoke<unknown>('archive.restore', { source }),
  purgeArchiveSource: (source: string) => invoke<unknown>('archive.purge', { source }),
  purgeArchive: () => invoke<unknown>('archive.purge'),
  listJobs: () => invoke<Job[]>('jobs.list'),
  listDownloads: () => invoke<Job[]>('downloads.list'),
  submitYoutubeDownload: (url: string, retryId?: string, cookieBrowser?: string) => invoke<Job>('downloads.submit', { url, ...(retryId ? { retry_id: retryId } : {}), ...(cookieBrowser ? { cookie_browser: cookieBrowser } : {}) }),
  listDownloadEvents: (jobId: string) => invoke<JobEvent[]>('downloads.events', { job_id: jobId }),
  cancelDownload: (jobId: string) => invoke<Job>('downloads.cancel', { job_id: jobId }),
  submitJob: (source: string, mode: Job['mode'], options?: JobSubmissionOptions) =>
    invoke<Job>('jobs.submit', { source, mode, ...options }),
  submitJobs: (sources: string[], mode: Job['mode']) =>
    invoke<JobSubmissionResult[]>('jobs.submit_many', { sources, mode }),
  listJobEvents: (jobId: string) => invoke<JobEvent[]>('jobs.events', { job_id: jobId }),
  cancelJob: (jobId: string) => invoke<Job>('jobs.cancel', { job_id: jobId }),
  selectDirectory: (defaultPath?: string) => bridge().selectDirectory(defaultPath),
  selectFile: (defaultPath?: string) => bridge().selectFile(defaultPath),
  openExternal: (url: string) => bridge().openExternal(url),
  openTranscodeFolder: () => bridge().openTranscodeFolder(),
  openOutput: (source: string) => bridge().openOutput(source),
  getDroppedFilePath: (file: File) => bridge().getPathForFile(file),
}

export type DesktopClient = typeof desktopClient

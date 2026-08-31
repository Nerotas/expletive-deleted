import type {
  Capabilities,
  ArchiveItem,
  DictionaryAction,
  DictionaryInfo,
  DictionaryTarget,
  InstallPlan,
  ImportResult,
  Job,
  JobEvent,
  JobSubmissionResult,
  LibraryItem,
  ReviewResult,
  Settings,
} from '../types/domain'

function bridge() {
  if (!window.profanityCensor) {
    throw new Error('The Electron preload bridge did not load. Restart the desktop application.')
  }
  return window.profanityCensor
}

function invoke<T>(method: string, params?: Record<string, unknown>): Promise<T> {
  return bridge().invoke<T>(method, params)
}

export const desktopClient = {
  getSettings: () => invoke<Settings>('settings.get'),
  updateSettings: (settings: Settings) => invoke<Settings>('settings.update', { settings }),
  getCapabilities: () => invoke<Capabilities>('capabilities.get'),
  getDictionary: () => invoke<DictionaryInfo>('dictionary.get'),
  updateDictionary: (action: DictionaryAction, target: DictionaryTarget, word: string) =>
    invoke<DictionaryInfo>(`dictionary.${action}`, { target, word }),
  getReview: (source: string) => invoke<ReviewResult>('reviews.list', { source }),
  planDependencies: (components: string[]) =>
    invoke<InstallPlan>('dependencies.plan', { components }),
  installDependencies: (planId: string) =>
    invoke<unknown>('dependencies.install', { plan_id: planId }),
  inspectExistingFfmpeg: (path: string) =>
    invoke<{ ffmpeg_path: string; ffprobe_path: string; version: string | null }>(
      'dependencies.inspect_ffmpeg',
      { path },
    ),
  locateExistingFfmpeg: (path: string) =>
    invoke<Capabilities>('dependencies.locate_ffmpeg', { path }),
  locateExistingModel: (path: string) =>
    invoke<Capabilities>('dependencies.locate_model', { path }),
  listLibrary: () => invoke<LibraryItem[]>('library.list'),
  archiveSource: (source: string) => invoke<unknown>('library.archive', { source }),
  importSources: (sources: string[]) => invoke<ImportResult[]>('library.import', { sources }),
  listArchive: () => invoke<ArchiveItem[]>('archive.list'),
  restoreArchiveSource: (source: string) => invoke<unknown>('archive.restore', { source }),
  purgeArchiveSource: (source: string) => invoke<unknown>('archive.purge', { source }),
  purgeArchive: () => invoke<unknown>('archive.purge'),
  listJobs: () => invoke<Job[]>('jobs.list'),
  submitJob: (source: string, mode: Job['mode']) =>
    invoke<Job>('jobs.submit', { source, mode }),
  submitJobs: (sources: string[], mode: Job['mode']) =>
    invoke<JobSubmissionResult[]>('jobs.submit_many', { sources, mode }),
  listJobEvents: (jobId: string) => invoke<JobEvent[]>('jobs.events', { job_id: jobId }),
  cancelJob: (jobId: string) => invoke<Job>('jobs.cancel', { job_id: jobId }),
  selectDirectory: (defaultPath?: string) => bridge().selectDirectory(defaultPath),
  selectFile: (defaultPath?: string) => bridge().selectFile(defaultPath),
  openExternal: (url: string) => bridge().openExternal(url),
  getDroppedFilePath: (file: File) => bridge().getPathForFile(file),
}

export type DesktopClient = typeof desktopClient

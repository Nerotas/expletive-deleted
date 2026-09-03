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
} from '../types/domain'

function bridge() {
  if (!window.expletiveDeleted) {
    throw new Error('The Electron preload bridge did not load. Restart the desktop application.')
  }
  return window.expletiveDeleted
}

function invoke<T>(method: string, params?: Record<string, unknown>): Promise<T> {
  return bridge().invoke<T>(method, params)
}

export const desktopClient = {
  getSettings: () => invoke<Settings>('settings.get'),
  updateSettings: (settings: Settings) => invoke<Settings>('settings.update', { settings }),
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
  importDictionary: (source: string) =>
    invoke<DictionaryMutationResult>('dictionary.import', { source }),
  exportDictionary: (destination: string) =>
    invoke<{ path: string }>('dictionary.export', { destination }),
  getReview: (source: string) => invoke<ReviewResult>('reviews.list', { source }),
  planDependencies: (components: string[]) =>
    invoke<InstallPlan>('dependencies.plan', { components }),
  installDependencies: (planId: string) =>
    invoke<InstallStatus>('dependencies.install', { plan_id: planId }),
  getInstallStatus: (installId: string) =>
    invoke<InstallStatus>('dependencies.status', { install_id: installId }),
  cancelInstall: (installId: string) =>
    invoke<InstallStatus>('dependencies.cancel', { install_id: installId }),
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
  submitJob: (source: string, mode: Job['mode'], options?: JobSubmissionOptions) =>
    invoke<Job>('jobs.submit', { source, mode, ...options }),
  submitJobs: (sources: string[], mode: Job['mode']) =>
    invoke<JobSubmissionResult[]>('jobs.submit_many', { sources, mode }),
  listJobEvents: (jobId: string) => invoke<JobEvent[]>('jobs.events', { job_id: jobId }),
  cancelJob: (jobId: string) => invoke<Job>('jobs.cancel', { job_id: jobId }),
  selectDirectory: (defaultPath?: string) => bridge().selectDirectory(defaultPath),
  selectFile: (defaultPath?: string) => bridge().selectFile(defaultPath),
  selectDictionaryImport: () => bridge().selectDictionaryImport(),
  selectDictionaryExport: () => bridge().selectDictionaryExport(),
  openExternal: (url: string) => bridge().openExternal(url),
  openFolder: (folderPath: string) => bridge().openFolder(folderPath),
  openFile: (filePath: string) => bridge().openFile(filePath),
  getDroppedFilePath: (file: File) => bridge().getPathForFile(file),
}

export type DesktopClient = typeof desktopClient

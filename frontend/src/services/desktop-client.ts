import type {
  Capabilities,
  DictionaryAction,
  DictionaryInfo,
  DictionaryTarget,
  InstallPlan,
  Job,
  JobEvent,
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
  listLibrary: () => invoke<LibraryItem[]>('library.list'),
  archiveSource: (source: string) => invoke<unknown>('library.archive', { source }),
  listJobs: () => invoke<Job[]>('jobs.list'),
  submitJob: (source: string, mode: Job['mode']) =>
    invoke<Job>('jobs.submit', { source, mode }),
  listJobEvents: (jobId: string) => invoke<JobEvent[]>('jobs.events', { job_id: jobId }),
  cancelJob: (jobId: string) => invoke<Job>('jobs.cancel', { job_id: jobId }),
  selectDirectory: (defaultPath?: string) => bridge().selectDirectory(defaultPath),
}

export type DesktopClient = typeof desktopClient


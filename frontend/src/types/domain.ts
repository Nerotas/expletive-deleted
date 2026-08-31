export type Page = 'queue' | 'dictionary' | 'settings'
export type Theme = 'light' | 'dark'
export type LibraryStatus = 'ready' | 'transcribed' | 'finished'
export type JobStatus =
  | 'queued'
  | 'transcribing'
  | 'transcribed'
  | 'censoring'
  | 'verifying'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type LibraryItem = {
  source: string
  status: LibraryStatus
  transcript: string | null
  output: string | null
}

export type ArchiveItem = {
  source: string
  relative_path: string
  size_bytes: number
  archived_at: string
}

export type ImportResult = {
  source: string
  destination?: string
  status: 'added' | 'already_exists' | 'unsupported' | 'unavailable' | 'failed'
  detail?: string
}

export type JobError = {
  code: string
  message: string
  detail: string | null
  retryable: boolean
}

export type Job = {
  id: string
  source: string
  mode: 'report_only' | 'censor'
  status: JobStatus
  progress_percent: number | null
  error: JobError | null
}

export type JobSubmissionCode =
  | 'already_queued'
  | 'existing_output'
  | 'invalid_mode'
  | 'outside_input'
  | 'unavailable'
  | 'unsupported'

export type JobSubmissionResult =
  | { source: string; status: 'queued'; job: Job }
  | { source: string; status: 'rejected'; code: JobSubmissionCode; detail: string }

export type JobEvent = {
  event: string
  job_id: string
  sequence: number
  stage: JobStatus | null
  percent: number | null
  eta_seconds: number | null
  fps: number | null
  message: string | null
}

export type WhisperLibrary = 'faster-whisper' | 'openai-whisper'
export type WhisperModel = 'tiny' | 'base' | 'small' | 'medium' | 'large-v3'

export type Capabilities = {
  ready: boolean
  ffmpeg: boolean
  ffprobe: boolean
  whisper: boolean
  whisper_library: WhisperLibrary
  whisper_model: WhisperModel
  whisper_model_ready: boolean
  whisper_device: string
  video_encoders: string[]
}

export type DictionaryTarget = 'censor' | 'exclude'
export type DictionaryAction = 'add' | 'remove'

export type DictionaryInfo = {
  words_path: string
  words_count: number
  words: string[]
  exclusions_path: string
  exclusions_count: number
  exclusions: string[]
  overrides_path: string
  overrides_count: number
  discovered_count: number
  discovered: string[]
  changed?: boolean
}

export type ReviewCandidate = {
  word: string
  start: number | null
  end: number | null
}

export type ReviewResult = {
  source: string
  candidates: ReviewCandidate[]
}

export type Settings = {
  schema_version: number
  directories: {
    input: string
    output: string
    archive: string
    transcripts: string
  }
  processing: {
    mode: 'report_only' | 'censor'
    device: 'auto' | 'cpu' | 'cuda'
  }
  censoring: {
    stereo_method: 'drop_audio' | 'karaoke'
    padding_before_ms: number
    padding_after_ms: number
  }
  audio: { surround_output: 'preserve_5_1' | 'downmix_stereo' }
  video: { mode: 'h264' | 'preserve_source' }
  whisper: { library: WhisperLibrary; model: WhisperModel }
  source: { archive_after_success: boolean; scan_subdirectories: boolean }
  runtime: {
    ffmpeg_path: string | null
    ffprobe_path: string | null
    whisper_cache: string | null
  }
}

export type InstallPlan = { plan_id: string }

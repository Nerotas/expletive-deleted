import type { Capabilities, DictionaryEntryPage, DictionaryMutationResult, Settings } from '../types/domain'

export const defaultSettings: Settings = {
  schema_version: 1,
  directories: {
    input: 'C:\\Media\\Ready',
    output: 'C:\\Media\\Finished',
    archive: 'C:\\Media\\Processed',
    transcripts: 'C:\\Media\\Transcripts',
  },
  processing: { mode: 'censor', device: 'auto' },
  censoring: {
    stereo_method: 'drop_audio',
    padding_before_ms: 100,
    padding_after_ms: 100,
  },
  audio: { surround_output: 'preserve_5_1' },
  video: { mode: 'h264' },
  whisper: { library: 'faster-whisper', model: 'large-v3' },
  source: { archive_after_success: false, scan_subdirectories: true },
  onboarding: { completed: true },
  runtime: { ffmpeg_path: null, ffprobe_path: null, whisper_cache: null },
}

export const readyCapabilities: Capabilities = {
  ready: true,
  ffmpeg: true,
  ffprobe: true,
  whisper: true,
  whisper_library: 'faster-whisper',
  whisper_model: 'large-v3',
  whisper_model_ready: true,
  whisper_device: 'cpu',
  video_encoders: ['libx264'],
}

export const emptyDictionary: DictionaryMutationResult = {
  dictionary_path: 'profanity.json',
  schema_version: 2,
  seeded_from_default_version: 1,
  words_count: 0,
  exclusions_count: 0,
}

export const emptyDictionaryPage: DictionaryEntryPage = {
  target: 'exclude',
  items: [],
  total: 0,
  page: 1,
  page_size: 25,
  total_pages: 0,
}


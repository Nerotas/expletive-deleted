import { createHash } from 'node:crypto'
import { execFileSync, spawnSync } from 'node:child_process'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'

const testDirectory = path.dirname(fileURLToPath(import.meta.url))
const auditScript = path.join(testDirectory, 'audit-bundled-runtime.mjs')
const runtimeDirectories: string[] = []

const componentVersions = {
  'faster-whisper': '1.2.1',
  ctranslate2: '4.8.1',
  numpy: '2.5.2',
  'better-profanity': '0.7.0',
  'huggingface-hub': '1.28.0',
  av: '18.1.0',
}
const licenses = [
  ['python.txt', 'PSF-2.0'],
  ['ffmpeg.txt', 'LGPL-2.1-or-later'],
  ['pyav.txt', 'BSD-3-Clause'],
  ['faster-whisper.txt', 'MIT'],
  ['ctranslate2.txt', 'MIT'],
  ['numpy.txt', 'BSD-3-Clause'],
  ['better-profanity.txt', 'MIT'],
  ['huggingface-hub.txt', 'Apache-2.0'],
  ['yt-dlp.txt', 'Unlicense'],
] as const

async function createRuntime() {
  const runtimeRoot = await mkdtemp(path.join(os.tmpdir(), 'expletive-deleted-runtime-'))
  runtimeDirectories.push(runtimeRoot)
  await mkdir(path.join(runtimeRoot, 'python'), { recursive: true })
  await mkdir(path.join(runtimeRoot, 'ffmpeg'), { recursive: true })
  await mkdir(path.join(runtimeRoot, 'yt-dlp'), { recursive: true })
  await mkdir(path.join(runtimeRoot, 'LICENSES'), { recursive: true })

  const files = new Map<string, string>()
  const addFile = async (relativePath: string, content: string) => {
    const absolutePath = path.join(runtimeRoot, relativePath)
    await writeFile(absolutePath, content)
    files.set(relativePath, createHash('sha256').update(content).digest('hex'))
  }

  await addFile('python/python.exe', 'synthetic-python')
  await addFile('ffmpeg/ffmpeg.exe', 'synthetic-ffmpeg')
  await addFile('ffmpeg/ffprobe.exe', 'synthetic-ffprobe')
  await addFile('yt-dlp/yt-dlp.exe', 'synthetic-yt-dlp')
  await addFile('ffmpeg-source.zip', 'synthetic-source')
  const configure = ['--disable-gpl', '--disable-nonfree', '--enable-shared']
  const build = {
    source_revision: 'synthetic-revision',
    source_url: 'https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz',
    version: '8.1.2',
    patches: [],
    compiler: 'synthetic-msvc',
    configure,
    source_archive: {
      path: 'ffmpeg-source.zip',
      sha256: files.get('ffmpeg-source.zip'),
    },
  }
  await addFile('ffmpeg-build.json', JSON.stringify(build))
  await addFile(
    'THIRD_PARTY_NOTICES.md',
    ['Python', 'FFmpeg', 'PyAV', 'faster-whisper', 'CTranslate2', 'NumPy', 'better-profanity', 'huggingface-hub', 'yt-dlp'].join('\n'),
  )
  for (const [fileName, license] of licenses) await addFile(`LICENSES/${fileName}`, `${license}\n`)

  const manifest = {
    schema_version: 1,
    platform: 'win32-x64',
    python: { path: 'python/python.exe', version: '3.13.7', license: 'PSF-2.0' },
    ffmpeg: {
      ffmpeg_path: 'ffmpeg/ffmpeg.exe',
      ffprobe_path: 'ffmpeg/ffprobe.exe',
      version: '8.1.2',
      license: 'LGPL-2.1-or-later',
      configure,
    },
    pyav: { version: componentVersions.av, license: 'BSD-3-Clause', ffmpeg_library_origin: 'bundled-lgpl-build' },
    ytdlp: {
      path: 'yt-dlp/yt-dlp.exe',
      version: '2026.08.19',
      source: 'https://github.com/yt-dlp/yt-dlp/releases/download/2026.08.19/yt-dlp.exe',
      license: 'Unlicense',
    },
    files: [...files].map(([filePath, sha256]) => ({ path: filePath, sha256 })),
    licenses: licenses.map(([fileName, spdx]) => ({ path: `LICENSES/${fileName}`, spdx })),
  }
  await writeFile(path.join(runtimeRoot, 'runtime-manifest.json'), JSON.stringify(manifest))

  const sbomComponents = [
    { name: 'Python', version: '3.13.7', license: 'PSF-2.0' },
    { name: 'FFmpeg', version: '8.1.2', license: 'LGPL-2.1-or-later' },
    { name: 'PyAV', version: componentVersions.av, license: 'BSD-3-Clause' },
    { name: 'yt-dlp', version: '2026.08.19', license: 'Unlicense' },
    ...Object.entries(componentVersions)
      .filter(([name]) => name !== 'av')
      .map(([name, version]) => ({ name, version, license: licenses.find(([fileName]) => fileName.startsWith(name))?.[1] ?? 'MIT' })),
  ]
  await addFile('sbom.cdx.json', JSON.stringify({ bomFormat: 'CycloneDX', components: sbomComponents.map(({ name, version, license }) => ({ name, version, licenses: [{ license: { id: license } }] })) }))
  const manifestWithSbom = JSON.parse(await readFile(path.join(runtimeRoot, 'runtime-manifest.json'), 'utf8'))
  manifestWithSbom.files.push({ path: 'sbom.cdx.json', sha256: files.get('sbom.cdx.json') })
  await writeFile(path.join(runtimeRoot, 'runtime-manifest.json'), JSON.stringify(manifestWithSbom))
  return runtimeRoot
}

afterEach(async () => {
  await Promise.all(runtimeDirectories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })))
})

describe('bundled runtime audit', () => {
  it('accepts a complete synthetic runtime payload', async () => {
    const runtimeRoot = await createRuntime()
    expect(() => execFileSync(process.execPath, [auditScript, runtimeRoot], { encoding: 'utf8' })).not.toThrow()
  })

  it('rejects an SBOM version that differs from requirements.txt', async () => {
    const runtimeRoot = await createRuntime()
    const sbomPath = path.join(runtimeRoot, 'sbom.cdx.json')
    const sbom = JSON.parse(await readFile(sbomPath, 'utf8'))
    sbom.components.find((component: { name: string }) => component.name === 'faster-whisper').version = '0.0.0'
    await writeFile(sbomPath, JSON.stringify(sbom))
    const manifestPath = path.join(runtimeRoot, 'runtime-manifest.json')
    const manifest = JSON.parse(await readFile(manifestPath, 'utf8'))
    const sbomHash = createHash('sha256').update(await readFile(sbomPath)).digest('hex')
    manifest.files.find((file: { path: string }) => file.path === 'sbom.cdx.json').sha256 = sbomHash
    await writeFile(manifestPath, JSON.stringify(manifest))

    const result = spawnSync(process.execPath, [auditScript, runtimeRoot], { encoding: 'utf8' })
    expect(result.status).not.toBe(0)
    expect(result.stderr).toMatch(/SBOM must identify faster-whisper 1\.2\.1 under MIT/)
  })
})
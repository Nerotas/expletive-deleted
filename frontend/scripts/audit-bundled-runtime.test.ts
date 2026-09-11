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

async function createRuntime() {
  const runtimeRoot = await mkdtemp(path.join(os.tmpdir(), 'expletive-deleted-python-runtime-'))
  runtimeDirectories.push(runtimeRoot)
  await mkdir(path.join(runtimeRoot, 'python'), { recursive: true })
  await mkdir(path.join(runtimeRoot, 'LICENSES'), { recursive: true })

  const files = new Map<string, string>()
  const addFile = async (relativePath: string, content: string) => {
    const absolutePath = path.join(runtimeRoot, relativePath)
    await mkdir(path.dirname(absolutePath), { recursive: true })
    await writeFile(absolutePath, content)
    files.set(relativePath, createHash('sha256').update(content).digest('hex'))
  }

  await addFile('python/python.exe', 'synthetic-python')
  await addFile('python/Lib/site-packages/pip/__init__.py', 'synthetic-pip')
  await addFile('THIRD_PARTY_NOTICES.md', 'Python\npip\n')
  await addFile('LICENSES/python.txt', 'PSF-2.0\n')
  await addFile('LICENSES/pip.txt', 'MIT\n')
  await addFile('sbom.cdx.json', JSON.stringify({
    bomFormat: 'CycloneDX',
    components: [
      { name: 'Python', version: '3.13.15', licenses: [{ license: { id: 'PSF-2.0' } }] },
      { name: 'pip', version: '25.2', licenses: [{ license: { id: 'MIT' } }] },
    ],
  }))

  const manifest = {
    schema_version: 2,
    platform: 'win32-x64',
    python: { path: 'python/python.exe', version: '3.13.15', license: 'PSF-2.0' },
    pip: { version: '25.2', license: 'MIT' },
    files: [...files].map(([filePath, sha256]) => ({ path: filePath, sha256 })),
    licenses: [
      { path: 'LICENSES/python.txt', spdx: 'PSF-2.0' },
      { path: 'LICENSES/pip.txt', spdx: 'MIT' },
    ],
  }
  await writeFile(path.join(runtimeRoot, 'runtime-manifest.json'), JSON.stringify(manifest))
  return runtimeRoot
}

async function refreshManifestHash(runtimeRoot: string, relativePath: string) {
  const manifestPath = path.join(runtimeRoot, 'runtime-manifest.json')
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'))
  const content = await readFile(path.join(runtimeRoot, relativePath))
  const sha256 = createHash('sha256').update(content).digest('hex')
  const record = manifest.files.find((file: { path: string }) => file.path === relativePath)
  if (record) record.sha256 = sha256
  else manifest.files.push({ path: relativePath, sha256 })
  await writeFile(manifestPath, JSON.stringify(manifest))
}

afterEach(async () => {
  await Promise.all(runtimeDirectories.splice(0).map((directory) => rm(directory, { recursive: true, force: true })))
})

describe('private Python runtime audit', () => {
  it('accepts a Python and pip bootstrap payload', async () => {
    const runtimeRoot = await createRuntime()
    expect(() => execFileSync(process.execPath, [auditScript, runtimeRoot], { encoding: 'utf8' })).not.toThrow()
  })

  it('rejects a legacy bundled media executable even when it is hashed', async () => {
    const runtimeRoot = await createRuntime()
    await writeFile(path.join(runtimeRoot, 'python', 'ffmpeg.exe'), 'synthetic-ffmpeg')
    await refreshManifestHash(runtimeRoot, 'python/ffmpeg.exe')

    const result = spawnSync(process.execPath, [auditScript, runtimeRoot], { encoding: 'utf8' })
    expect(result.status).not.toBe(0)
    expect(result.stderr).toMatch(/python\/ffmpeg\.exe/)
  })

  it('rejects versioned GPL encoder libraries even when they are hashed', async () => {
    const runtimeRoot = await createRuntime()
    const relativePath = 'python/DLLs/libx264-164.dll'
    await mkdir(path.dirname(path.join(runtimeRoot, relativePath)), { recursive: true })
    await writeFile(path.join(runtimeRoot, relativePath), 'synthetic-libx264')
    await refreshManifestHash(runtimeRoot, relativePath)

    const result = spawnSync(process.execPath, [auditScript, runtimeRoot], { encoding: 'utf8' })
    expect(result.status).not.toBe(0)
    expect(result.stderr).toMatch(/libx264-164\.dll/)
  })

  it('rejects processing packages from the release payload', async () => {
    const runtimeRoot = await createRuntime()
    const relativePath = 'python/Lib/site-packages/faster_whisper/__init__.py'
    await mkdir(path.dirname(path.join(runtimeRoot, relativePath)), { recursive: true })
    await writeFile(path.join(runtimeRoot, relativePath), 'synthetic-package')
    await refreshManifestHash(runtimeRoot, relativePath)

    const result = spawnSync(process.execPath, [auditScript, runtimeRoot], { encoding: 'utf8' })
    expect(result.status).not.toBe(0)
    expect(result.stderr).toMatch(/faster_whisper/)
  })

  it('rejects an SBOM version that differs from the manifest', async () => {
    const runtimeRoot = await createRuntime()
    const sbomPath = path.join(runtimeRoot, 'sbom.cdx.json')
    const sbom = JSON.parse(await readFile(sbomPath, 'utf8'))
    sbom.components.find((component: { name: string }) => component.name === 'pip').version = '0.0.0'
    await writeFile(sbomPath, JSON.stringify(sbom))
    await refreshManifestHash(runtimeRoot, 'sbom.cdx.json')

    const result = spawnSync(process.execPath, [auditScript, runtimeRoot], { encoding: 'utf8' })
    expect(result.status).not.toBe(0)
    expect(result.stderr).toMatch(/SBOM must identify pip 25\.2 under MIT/)
  })
})

import { createHash } from 'node:crypto'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'

import { afterEach, describe, expect, it, vi } from 'vitest'

import refreshBundledRuntimeManifestAfterSign from './refresh-bundled-runtime-manifest-after-sign.mjs'

const temporaryRoots = []

afterEach(async () => {
  await Promise.all(temporaryRoots.splice(0).map((root) => rm(root, { recursive: true, force: true })))
})

describe('refreshBundledRuntimeManifestAfterSign', () => {
  it('records hashes for executable bytes changed by Azure signing', async () => {
    vi.spyOn(console, 'log').mockImplementation(() => {})
    const appOutDir = await mkdtemp(path.join(os.tmpdir(), 'signed-runtime-manifest-'))
    temporaryRoots.push(appOutDir)

    const runtimeRoot = path.join(appOutDir, 'resources', 'app-runtime')
    const executable = path.join(runtimeRoot, 'python', 'python.exe')
    const license = path.join(runtimeRoot, 'LICENSES', 'python.txt')
    const manifestPath = path.join(runtimeRoot, 'runtime-manifest.json')
    await mkdir(path.dirname(executable), { recursive: true })
    await mkdir(path.dirname(license), { recursive: true })
    await writeFile(executable, 'signed executable bytes')
    await writeFile(license, 'license text')
    const recordedPaths = ['python/python.exe', 'LICENSES/python.txt']
      .sort((left, right) => right.localeCompare(left))
    await writeFile(manifestPath, JSON.stringify({
      schema_version: 2,
      files: recordedPaths.map((filePath) => ({ path: filePath, sha256: '0'.repeat(64) })),
    }))

    await refreshBundledRuntimeManifestAfterSign({ electronPlatformName: 'win32', appOutDir })

    const manifest = JSON.parse(await readFile(manifestPath, 'utf8'))
    const expectedFiles = [
      { path: 'python/python.exe', sha256: createHash('sha256').update(await readFile(executable)).digest('hex') },
      { path: 'LICENSES/python.txt', sha256: createHash('sha256').update(await readFile(license)).digest('hex') },
    ].sort((left, right) => left.path.localeCompare(right.path))
    expect(manifest.files).toEqual(expectedFiles)
  })

  it('rejects file-set changes after the source runtime audit', async () => {
    vi.spyOn(console, 'log').mockImplementation(() => {})
    const appOutDir = await mkdtemp(path.join(os.tmpdir(), 'changed-runtime-manifest-'))
    temporaryRoots.push(appOutDir)

    const runtimeRoot = path.join(appOutDir, 'resources', 'app-runtime')
    await mkdir(path.join(runtimeRoot, 'python'), { recursive: true })
    await writeFile(path.join(runtimeRoot, 'python', 'python.exe'), 'signed executable bytes')
    await writeFile(path.join(runtimeRoot, 'python', 'unexpected.exe'), 'unexpected executable')
    await writeFile(path.join(runtimeRoot, 'runtime-manifest.json'), JSON.stringify({
      schema_version: 2,
      files: [{ path: 'python/python.exe', sha256: '0'.repeat(64) }],
    }))

    await expect(refreshBundledRuntimeManifestAfterSign({
      electronPlatformName: 'win32',
      appOutDir,
    })).rejects.toThrow('Signing changed the audited private runtime file set')
  })
})

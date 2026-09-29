import { createHash } from 'node:crypto'
import { access, readFile, readdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export async function generateBundledRuntimeManifest(suppliedDirectory, options = {}) {
  if (!suppliedDirectory) throw new Error('Pass the completed runtime directory or set BUNDLED_RUNTIME_DIR.')

  const runtimeRoot = path.resolve(suppliedDirectory)
  const manifestPath = path.join(runtimeRoot, 'runtime-manifest.json')
  await access(manifestPath)

  const hashFile = async (filePath) => createHash('sha256').update(await readFile(filePath)).digest('hex')
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'))

  const artifacts = []
  async function inspect(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const absolutePath = path.join(directory, entry.name)
      const relativePath = path.relative(runtimeRoot, absolutePath).replaceAll('\\', '/')
      if (entry.isDirectory()) {
        await inspect(absolutePath)
        continue
      }
      if (relativePath === 'runtime-manifest.json') continue
      artifacts.push({ path: relativePath, sha256: await hashFile(absolutePath) })
    }
  }

  await inspect(runtimeRoot)
  artifacts.sort((left, right) => left.path.localeCompare(right.path))

  if (options.preserveFileSet) {
    const recordedPaths = (manifest.files ?? []).map((file) => file.path).sort()
    const artifactPaths = artifacts.map((file) => file.path)
    if (JSON.stringify(recordedPaths) !== JSON.stringify(artifactPaths)) {
      throw new Error('Signing changed the audited private runtime file set; refusing to replace its manifest.')
    }
  }

  manifest.files = artifacts
  await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`)
  return artifacts.length
}

const isDirectInvocation = process.argv[1]
  && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
if (isDirectInvocation) {
  const suppliedDirectory = process.argv[2] ?? process.env.BUNDLED_RUNTIME_DIR
  const artifactCount = await generateBundledRuntimeManifest(suppliedDirectory)
  console.log(`Generated ${artifactCount} runtime artifact hashes: ${path.resolve(suppliedDirectory, 'runtime-manifest.json')}`)
}

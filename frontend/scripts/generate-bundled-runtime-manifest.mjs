import { createHash } from 'node:crypto'
import { access, readFile, readdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

const suppliedDirectory = process.argv[2] ?? process.env.BUNDLED_RUNTIME_DIR
if (!suppliedDirectory) throw new Error('Pass the completed runtime directory or set BUNDLED_RUNTIME_DIR.')

const runtimeRoot = path.resolve(suppliedDirectory)
const manifestPath = path.join(runtimeRoot, 'runtime-manifest.json')
const buildPath = path.join(runtimeRoot, 'ffmpeg-build.json')
const sourceArchivePath = path.join(runtimeRoot, 'ffmpeg-source.zip')
await Promise.all([access(manifestPath), access(buildPath), access(sourceArchivePath)])

const hashFile = async (filePath) => createHash('sha256').update(await readFile(filePath)).digest('hex')
const manifest = JSON.parse(await readFile(manifestPath, 'utf8'))
const build = JSON.parse(await readFile(buildPath, 'utf8'))
const sourceArchive = 'ffmpeg-source.zip'
build.source_archive = { path: sourceArchive, sha256: await hashFile(sourceArchivePath) }
await writeFile(buildPath, `${JSON.stringify(build, null, 2)}\n`)

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
manifest.files = artifacts
await writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`)
console.log(`Generated ${artifacts.length} runtime artifact hashes: ${manifestPath}`)

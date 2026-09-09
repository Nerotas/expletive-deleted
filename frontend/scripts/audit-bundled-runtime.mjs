import { createHash } from 'node:crypto'
import { access, readFile, readdir } from 'node:fs/promises'
import path from 'node:path'

const suppliedDirectory = process.argv[2] ?? process.env.BUNDLED_RUNTIME_DIR
if (!suppliedDirectory) throw new Error('Pass the staged runtime directory or set BUNDLED_RUNTIME_DIR.')

const runtimeRoot = path.resolve(suppliedDirectory)
const requiredFiles = [
  'python/python.exe',
  'ffmpeg/ffmpeg.exe',
  'ffmpeg/ffprobe.exe',
  'THIRD_PARTY_NOTICES.md',
  'sbom.cdx.json',
  'ffmpeg-source.zip',
  'ffmpeg-build.json',
  'runtime-manifest.json',
]
const forbiddenNames = new Set(['libx264.dll', 'libx265.dll', 'yt-dlp.exe', 'model.bin'])
const forbiddenFragments = ['models--', 'whisper-cache']
const requiredSbomComponents = [
  { label: 'Python', names: ['python', 'cpython'], license: 'PSF-2.0' },
  { label: 'FFmpeg', names: ['ffmpeg'], license: 'LGPL-2.1-or-later' },
  { label: 'PyAV', names: ['pyav', 'av'], license: 'BSD-3-Clause' },
  { label: 'faster-whisper', names: ['faster-whisper'], license: 'MIT' },
  { label: 'CTranslate2', names: ['ctranslate2'], license: 'MIT' },
]

for (const relativePath of requiredFiles) await access(path.join(runtimeRoot, relativePath))
await access(path.join(runtimeRoot, 'LICENSES'))

const hash = async (relativePath) => createHash('sha256')
  .update(await readFile(path.join(runtimeRoot, relativePath)))
  .digest('hex')

const manifest = JSON.parse(await readFile(path.join(runtimeRoot, 'runtime-manifest.json'), 'utf8'))
const manifestErrors = []
if (manifest.schema_version !== 1) manifestErrors.push('schema_version must be 1')
if (manifest.platform !== 'win32-x64') manifestErrors.push('platform must be win32-x64')
if (manifest.python?.path !== 'python/python.exe' || manifest.python?.license !== 'PSF-2.0') {
  manifestErrors.push('python must identify python/python.exe under PSF-2.0')
}
if (
  manifest.ffmpeg?.ffmpeg_path !== 'ffmpeg/ffmpeg.exe'
  || manifest.ffmpeg?.ffprobe_path !== 'ffmpeg/ffprobe.exe'
  || manifest.ffmpeg?.license !== 'LGPL-2.1-or-later'
) manifestErrors.push('ffmpeg must identify the approved executable paths under LGPL-2.1-or-later')
if (manifest.pyav?.license !== 'BSD-3-Clause' || manifest.pyav?.ffmpeg_library_origin !== 'bundled-lgpl-build') {
  manifestErrors.push('pyav must identify its BSD-3-Clause license and approved LGPL FFmpeg library origin')
}
const configure = manifest.ffmpeg?.configure
if (!Array.isArray(configure) || configure.some((argument) => argument === '--enable-gpl' || argument === '--enable-nonfree')) {
  manifestErrors.push('ffmpeg configure arguments must be present and exclude --enable-gpl and --enable-nonfree')
}
if (!Array.isArray(manifest.files) || manifest.files.length === 0) manifestErrors.push('files must record hashed packaged artifacts')
if (!Array.isArray(manifest.licenses) || manifest.licenses.length === 0) manifestErrors.push('licenses must record shipped license texts')
if (manifestErrors.length) throw new Error(`Bundled runtime manifest violation:\n- ${manifestErrors.join('\n- ')}`)

const violations = []
const artifacts = new Map()
async function inspect(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const absolutePath = path.join(directory, entry.name)
    const relativePath = path.relative(runtimeRoot, absolutePath).replaceAll('\\', '/')
    if (entry.isDirectory()) {
      if (forbiddenFragments.some((fragment) => entry.name.toLowerCase().includes(fragment))) violations.push(relativePath)
      await inspect(absolutePath)
      continue
    }
    const normalizedName = entry.name.toLowerCase()
    if (forbiddenNames.has(normalizedName)) violations.push(relativePath)
    artifacts.set(relativePath, createHash('sha256').update(await readFile(absolutePath)).digest('hex'))
  }
}
await inspect(runtimeRoot)

const manifestFiles = new Map()
for (const file of manifest.files) {
  if (!file || typeof file.path !== 'string' || typeof file.sha256 !== 'string') {
    violations.push('manifest has an invalid file record')
    continue
  }
  if (file.path === 'runtime-manifest.json') {
    violations.push('runtime-manifest.json cannot hash itself; exclude it from files')
    continue
  }
  if (manifestFiles.has(file.path)) violations.push(`manifest repeats ${file.path}`)
  manifestFiles.set(file.path, file.sha256)
  const actualHash = artifacts.get(file.path)
  if (!actualHash) violations.push(`manifest artifact is absent: ${file.path}`)
  else if (actualHash !== file.sha256) violations.push(`manifest hash does not match: ${file.path}`)
}
for (const artifact of artifacts.keys()) {
  if (artifact !== 'runtime-manifest.json' && !manifestFiles.has(artifact)) {
    violations.push(`packaged artifact is not in the manifest: ${artifact}`)
  }
}

const licenseIds = new Set()
for (const license of manifest.licenses) {
  if (!license || typeof license.path !== 'string' || typeof license.spdx !== 'string') {
    violations.push('manifest has an invalid license record')
    continue
  }
  if (!license.path.startsWith('LICENSES/')) violations.push(`license is outside LICENSES/: ${license.path}`)
  if (!artifacts.has(license.path)) violations.push(`license text is absent: ${license.path}`)
  if (!manifestFiles.has(license.path)) violations.push(`license text is not hashed: ${license.path}`)
  licenseIds.add(license.spdx)
}
for (const licenseId of new Set(requiredSbomComponents.map((component) => component.license))) {
  if (!licenseIds.has(licenseId)) violations.push(`required license text is not recorded: ${licenseId}`)
}

const build = JSON.parse(await readFile(path.join(runtimeRoot, 'ffmpeg-build.json'), 'utf8'))
if (typeof build.source_revision !== 'string' || !build.source_revision) violations.push('ffmpeg-build.json needs source_revision')
if (!Array.isArray(build.patches)) violations.push('ffmpeg-build.json needs patches')
if (typeof build.compiler !== 'string' || !build.compiler) violations.push('ffmpeg-build.json needs compiler')
if (!Array.isArray(build.configure) || JSON.stringify(build.configure) !== JSON.stringify(configure)) {
  violations.push('ffmpeg-build.json configure must exactly match runtime manifest')
}
if (build.source_archive?.path !== 'ffmpeg-source.zip' || build.source_archive?.sha256 !== await hash('ffmpeg-source.zip')) {
  violations.push('ffmpeg-build.json source archive hash does not match ffmpeg-source.zip')
}

const sbom = JSON.parse(await readFile(path.join(runtimeRoot, 'sbom.cdx.json'), 'utf8'))
if (sbom.bomFormat !== 'CycloneDX' || !Array.isArray(sbom.components)) {
  violations.push('sbom.cdx.json must be a CycloneDX document with components')
} else {
  for (const requirement of requiredSbomComponents) {
    const component = sbom.components.find((candidate) => requirement.names.includes(String(candidate.name).toLowerCase()))
    const componentLicenses = component?.licenses ?? []
    const hasLicense = componentLicenses.some((entry) => entry?.license?.id === requirement.license)
    if (!component || !hasLicense) violations.push(`SBOM must identify ${requirement.label} under ${requirement.license}`)
  }
}

if (violations.length) throw new Error(`Bundled runtime artifact violation:\n- ${violations.join('\n- ')}`)

console.log(`Bundled Windows runtime audit passed: ${runtimeRoot}`)

import { createHash } from 'node:crypto'
import { access, readFile, readdir } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const suppliedDirectory = process.argv[2] ?? process.env.BUNDLED_RUNTIME_DIR
if (!suppliedDirectory) throw new Error('Pass the staged runtime directory or set BUNDLED_RUNTIME_DIR.')

const runtimeRoot = path.resolve(suppliedDirectory)
const scriptDirectory = path.dirname(fileURLToPath(import.meta.url))
const buildInputs = JSON.parse(await readFile(path.join(scriptDirectory, '..', 'runtime', 'windows-x64', 'build-inputs.json'), 'utf8'))
const requiredFiles = [
  'python/python.exe',
  'THIRD_PARTY_NOTICES.md',
  'sbom.cdx.json',
  'runtime-manifest.json',
]
const allowedTopLevelEntries = new Set([
  'python',
  'LICENSES',
  'THIRD_PARTY_NOTICES.md',
  'sbom.cdx.json',
  'runtime-manifest.json',
])
const forbiddenNames = new Set([
  'ffmpeg.exe',
  'ffprobe.exe',
  'yt-dlp.exe',
  'deno.exe',
  'model.bin',
])
const forbiddenFragments = [
  'models--',
  'whisper-cache',
  '/site-packages/av/',
  '/site-packages/av-',
  '/site-packages/better_profanity/',
  '/site-packages/better_profanity-',
  '/site-packages/ctranslate2/',
  '/site-packages/ctranslate2-',
  '/site-packages/faster_whisper/',
  '/site-packages/faster_whisper-',
  '/site-packages/huggingface_hub/',
  '/site-packages/huggingface_hub-',
  '/site-packages/numpy/',
  '/site-packages/numpy-',
  '/site-packages/numpy.libs/',
]
const forbiddenMediaLibrary = /^(?:avcodec|avdevice|avfilter|avformat|avutil|postproc|swresample|swscale)-?\d*\.dll$/i
const forbiddenGplEncoderLibrary = /^libx(?:264|265)(?:-\d+)?\.dll$/i
for (const relativePath of requiredFiles) await access(path.join(runtimeRoot, relativePath))
await access(path.join(runtimeRoot, 'LICENSES'))

const manifest = JSON.parse(await readFile(path.join(runtimeRoot, 'runtime-manifest.json'), 'utf8'))
const requiredSbomComponents = [
  { label: 'Python', names: ['python', 'cpython'], version: manifest.python?.version, license: 'PSF-2.0' },
  { label: 'pip', names: ['pip'], version: manifest.pip?.version, license: 'MIT' },
]
const manifestErrors = []
if (manifest.schema_version !== 2) manifestErrors.push('schema_version must be 2')
if (manifest.platform !== 'win32-x64') manifestErrors.push('platform must be win32-x64')
if (
  manifest.python?.path !== 'python/python.exe'
  || manifest.python?.version !== buildInputs.python?.version
  || manifest.python?.license !== 'PSF-2.0'
) manifestErrors.push(`python must identify python/python.exe version ${buildInputs.python?.version} under PSF-2.0`)
if (manifest.pip?.version !== buildInputs.pip?.version || manifest.pip?.license !== 'MIT') {
  manifestErrors.push(`pip must identify bootstrap version ${buildInputs.pip?.version} under MIT`)
}
for (const forbiddenField of ['ffmpeg', 'pyav', 'ytdlp', 'deno']) {
  if (forbiddenField in manifest) manifestErrors.push(`${forbiddenField} cannot be part of a Python-only runtime manifest`)
}
if (!Array.isArray(manifest.files) || manifest.files.length === 0) manifestErrors.push('files must record hashed packaged artifacts')
if (!Array.isArray(manifest.licenses) || manifest.licenses.length === 0) manifestErrors.push('licenses must record shipped license texts')
if (manifestErrors.length) throw new Error(`Private Python runtime manifest violation:\n- ${manifestErrors.join('\n- ')}`)

const violations = []
const artifacts = new Map()
async function inspect(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const absolutePath = path.join(directory, entry.name)
    const relativePath = path.relative(runtimeRoot, absolutePath).replaceAll('\\', '/')
    const normalizedPath = `/${relativePath.toLowerCase()}`
    if (path.dirname(absolutePath) === runtimeRoot && !allowedTopLevelEntries.has(entry.name)) {
      violations.push(`unexpected top-level runtime entry: ${relativePath}`)
    }
    if (entry.isDirectory()) {
      if (forbiddenFragments.some((fragment) => normalizedPath.includes(fragment))) violations.push(relativePath)
      await inspect(absolutePath)
      continue
    }
    const normalizedName = entry.name.toLowerCase()
    if (
      forbiddenNames.has(normalizedName)
      || forbiddenMediaLibrary.test(normalizedName)
      || forbiddenGplEncoderLibrary.test(normalizedName)
      || normalizedName.endsWith('.whl')
      || normalizedName.endsWith('.pt')
      || forbiddenFragments.some((fragment) => normalizedPath.includes(fragment))
    ) violations.push(relativePath)
    artifacts.set(relativePath, createHash('sha256').update(await readFile(absolutePath)).digest('hex'))
  }
}
await inspect(runtimeRoot)

const manifestFiles = new Map()
for (const file of manifest.files) {
  if (!file || typeof file.path !== 'string' || !/^[a-f0-9]{64}$/.test(file.sha256 ?? '')) {
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

const notices = (await readFile(path.join(runtimeRoot, 'THIRD_PARTY_NOTICES.md'), 'utf8')).toLowerCase()
for (const component of requiredSbomComponents) {
  if (!component.names.some((name) => notices.includes(name))) violations.push(`third-party notices must identify ${component.label}`)
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

const sbom = JSON.parse(await readFile(path.join(runtimeRoot, 'sbom.cdx.json'), 'utf8'))
if (sbom.bomFormat !== 'CycloneDX' || !Array.isArray(sbom.components)) {
  violations.push('sbom.cdx.json must be a CycloneDX document with components')
} else {
  for (const requirement of requiredSbomComponents) {
    const component = sbom.components.find((candidate) => requirement.names.includes(String(candidate.name).toLowerCase()))
    const componentLicenses = component?.licenses ?? []
    const hasLicense = componentLicenses.some((entry) => entry?.license?.id === requirement.license)
    if (!component || !hasLicense || component.version !== requirement.version) {
      violations.push(`SBOM must identify ${requirement.label} ${requirement.version} under ${requirement.license}`)
    }
  }
  const allowedNames = new Set(requiredSbomComponents.flatMap((component) => component.names))
  for (const component of sbom.components) {
    if (!allowedNames.has(String(component.name).toLowerCase())) {
      violations.push(`SBOM identifies a non-bootstrap bundled component: ${component.name}`)
    }
  }
}

if (violations.length) throw new Error(`Private Python runtime artifact violation:\n- ${[...new Set(violations)].join('\n- ')}`)

console.log(`Private Python runtime audit passed: ${runtimeRoot}`)

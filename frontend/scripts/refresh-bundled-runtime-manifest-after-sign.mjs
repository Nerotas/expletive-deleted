import path from 'node:path'

import { generateBundledRuntimeManifest } from './generate-bundled-runtime-manifest.mjs'

export default async function refreshBundledRuntimeManifestAfterSign(context) {
  if (context.electronPlatformName !== 'win32') return

  // Azure signing changes the packaged executable bytes after the source runtime audit.
  const runtimeRoot = path.join(context.appOutDir, 'resources', 'app-runtime')
  const artifactCount = await generateBundledRuntimeManifest(runtimeRoot, { preserveFileSet: true })
  console.log(`Refreshed ${artifactCount} signed runtime artifact hashes: ${runtimeRoot}`)
}

import { copyFile, mkdir } from 'node:fs/promises'
import path from 'node:path'

const iconName = 'profanity-censor-icon.ico'
const source = path.join(process.cwd(), 'src', 'assets', iconName)
const destinationDirectory = path.join(process.cwd(), 'out', 'assets')

await mkdir(destinationDirectory, { recursive: true })
await copyFile(source, path.join(destinationDirectory, iconName))

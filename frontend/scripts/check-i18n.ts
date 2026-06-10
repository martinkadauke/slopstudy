import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))

const en = JSON.parse(readFileSync(resolve(__dirname, '../src/i18n/en.json'), 'utf-8'))
const de = JSON.parse(readFileSync(resolve(__dirname, '../src/i18n/de.json'), 'utf-8'))

function walkKeys(obj: Record<string, unknown>, prefix = ''): string[] {
  const keys: string[] = []
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      keys.push(...walkKeys(value as Record<string, unknown>, fullKey))
    } else {
      keys.push(fullKey)
    }
  }
  return keys
}

function getByPath(obj: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce((acc: unknown, key) => {
    if (acc !== null && acc !== undefined && typeof acc === 'object') {
      return (acc as Record<string, unknown>)[key]
    }
    return undefined
  }, obj)
}

const enKeys = walkKeys(en)
const missing = enKeys.filter((key) => getByPath(de, key) === undefined)

if (missing.length === 0) {
  console.log('✓ All en.json keys present in de.json')
  process.exit(0)
} else {
  console.error(`✗ ${missing.length} key(s) in en.json missing from de.json:`)
  for (const key of missing) {
    console.error(`  - ${key}`)
  }
  process.exit(1)
}

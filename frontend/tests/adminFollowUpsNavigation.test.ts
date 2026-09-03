import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

function source(relative: string): string {
  return readFileSync(fileURLToPath(new URL(relative, import.meta.url)), 'utf-8')
}

const ADMIN_HOME_SOURCE = source('../src/pages/admin/AdminHomePage.vue')
const ROUTER_SOURCE = source('../src/router/index.ts')

function blockAfter(sourceText: string, marker: string): string {
  const start = sourceText.indexOf(marker)
  expect(start).toBeGreaterThanOrEqual(0)
  const end = sourceText.indexOf('\n  },', start)
  expect(end).toBeGreaterThan(start)
  return sourceText.slice(start, end)
}

describe('pending follow-ups admin navigation', () => {
  it('keeps the admin home entry out of the debug-only filter', () => {
    const entry = blockAfter(ADMIN_HOME_SOURCE, "to: '/admin/follow-ups'")
    expect(entry).toContain("group: 'behavior'")
    expect(entry).not.toContain('debugOnly')
  })

  it('keeps the direct route out of the debug-only guard', () => {
    const route = blockAfter(ROUTER_SOURCE, "path: 'follow-ups'")
    expect(route).toContain("name: 'admin-follow-ups'")
    expect(route).not.toContain('debugOnly')
  })
})

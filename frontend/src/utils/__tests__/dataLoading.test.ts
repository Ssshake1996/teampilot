import { describe, expect, it } from 'vitest'
import { fetchAllPages } from '../pagination'
import { readRememberedAccount, saveRememberedAccount } from '../rememberedAccount'

describe('complete paginated loading', () => {
  it('loads beyond the first 500 items without duplicating page one', async () => {
    const pages: number[] = []
    const items = await fetchAllPages(async page => {
      pages.push(page)
      return { data: { items: Array.from({ length: page === 3 ? 1 : 500 }, (_, i) => (page - 1) * 500 + i), total: 1001, page, page_size: 500 } }
    })
    expect(pages).toEqual([1, 2, 3])
    expect(items).toHaveLength(1001)
    expect(new Set(items).size).toBe(1001)
  })
})

describe('remembered account', () => {
  it('removes legacy plaintext passwords and only persists a username', () => {
    const values = new Map([['teampilot.rememberedLogin', JSON.stringify({ username: 'test', password: 'secret' })]])
    const storage = { getItem: (k: string) => values.get(k) ?? null, setItem: (k: string, v: string) => values.set(k, v), removeItem: (k: string) => values.delete(k) } as Storage
    expect(readRememberedAccount(storage)).toBe('test')
    expect([...values.values()].join('')).not.toContain('secret')
    saveRememberedAccount(storage, 'other', false)
    expect(values.size).toBe(0)
  })
})

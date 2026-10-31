import type { PaginatedResponse } from '@/types/models'

export async function fetchAllPages<T>(fetchPage: (page: number) => Promise<{ data: PaginatedResponse<T> }>): Promise<T[]> {
  const first = (await fetchPage(1)).data
  const items = [...first.items]
  const pages = Math.ceil(first.total / first.page_size)
  for (let page = 2; page <= pages; page++) {
    items.push(...(await fetchPage(page)).data.items)
  }
  return items
}

export interface FlatTaskRow {
  id: string
  _parentId?: string | null
  _depth?: number
  children?: FlatTaskRow[]
  [key: string]: unknown
}

export function flattenTaskTree(roots: FlatTaskRow[]): FlatTaskRow[] {
  const list: FlatTaskRow[] = []
  const walk = (items: FlatTaskRow[], depth: number, parentId: string | null) => {
    for (const item of items) {
      list.push({ ...item, _depth: depth, _parentId: parentId })
      if (item.children?.length) walk(item.children, depth + 1, item.id)
    }
  }
  walk(roots, 0, null)
  return list
}

export function taskMap(tree: FlatTaskRow[]) {
  return new Map(tree.map((task) => [task.id, task]))
}

export function ancestorAtDepth(tree: FlatTaskRow[], task: FlatTaskRow, depth: number) {
  const byId = taskMap(tree)
  let current: FlatTaskRow | undefined = task
  while (current && (current._depth || 0) > depth) {
    current = byId.get(current._parentId || '')
  }
  return current && current._depth === depth ? current : null
}

export function sameTaskSortScope(a: FlatTaskRow | null | undefined, b: FlatTaskRow | null | undefined) {
  return (a?._parentId || null) === (b?._parentId || null)
}

export function scopePeerForRow(tree: FlatTaskRow[], row: FlatTaskRow | null | undefined, scopeTask: FlatTaskRow | null | undefined) {
  if (!row || !scopeTask || (row._depth || 0) < (scopeTask._depth || 0)) return null
  const peer = ancestorAtDepth(tree, row, scopeTask._depth || 0)
  return peer && sameTaskSortScope(peer, scopeTask) ? peer : null
}

export function childrenByParent(tree: FlatTaskRow[]) {
  const map = new Map<string, FlatTaskRow[]>()
  for (const row of tree) {
    if (!row._parentId) continue
    const children = map.get(row._parentId) || []
    children.push(row)
    map.set(row._parentId, children)
  }
  return map
}

export function hasTaskChildren(tree: FlatTaskRow[], taskId: string) {
  return tree.some((row) => row._parentId === taskId)
}

export function descendantRows(tree: FlatTaskRow[], task: FlatTaskRow) {
  const byParent = childrenByParent(tree)
  const rows: FlatTaskRow[] = []

  function appendChildren(parentId: string) {
    for (const child of byParent.get(parentId) || []) {
      rows.push(child)
      appendChildren(child.id)
    }
  }

  appendChildren(task.id)
  return rows
}

export function getVisibleTaskRows(tree: FlatTaskRow[], collapsedIds: Set<string>) {
  const hiddenParentIds = new Set<string>()
  const visible: FlatTaskRow[] = []

  for (const row of tree) {
    if (row._parentId && hiddenParentIds.has(row._parentId)) {
      hiddenParentIds.add(row.id)
      continue
    }

    visible.push(row)
    if (collapsedIds.has(row.id)) {
      hiddenParentIds.add(row.id)
    }
  }

  return visible
}

export function orderedSiblingsForTask(tree: FlatTaskRow[], moved: FlatTaskRow) {
  const ordered: FlatTaskRow[] = []
  const seen = new Set<string>()

  for (const row of tree) {
    const peer = scopePeerForRow(tree, row, moved)
    if (!peer) continue
    if (peer.id === moved.id && row.id !== moved.id) continue
    if (seen.has(peer.id)) continue
    seen.add(peer.id)
    ordered.push(peer)
  }

  return ordered
}

export function normalizeTaskTreeForScope(tree: FlatTaskRow[], moved: FlatTaskRow, orderedSiblings: FlatTaskRow[]) {
  const siblingIds = new Set(orderedSiblings.map((task) => task.id))
  const result: FlatTaskRow[] = []
  let emittedScope = false

  for (const row of tree) {
    const peer = scopePeerForRow(tree, row, moved)
    if (peer && siblingIds.has(peer.id)) {
      if (!emittedScope) {
        for (const sibling of orderedSiblings) {
          result.push(sibling, ...descendantRows(tree, sibling))
        }
        emittedScope = true
      }
      continue
    }
    result.push(row)
  }

  return result
}

export function moveVisibleRow(tree: FlatTaskRow[], oldIndex: number, newIndex: number) {
  const next = [...tree]
  const [moved] = next.splice(oldIndex, 1)
  if (!moved) return next
  next.splice(newIndex, 0, moved)
  return next
}

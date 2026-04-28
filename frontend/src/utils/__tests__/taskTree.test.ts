import { describe, expect, it } from 'vitest'
import {
  flattenTaskTree,
  getVisibleTaskRows,
  hasTaskChildren,
  moveVisibleRow,
  normalizeTaskTreeForScope,
  orderedSiblingsForTask,
  type FlatTaskRow,
} from '../taskTree'

function ids(rows: FlatTaskRow[]) {
  return rows.map((row) => row.id)
}

const tree = flattenTaskTree([
  {
    id: 'a',
    title: 'A',
    children: [
      { id: 'a1', title: 'A1' },
      { id: 'a2', title: 'A2' },
    ],
  },
  {
    id: 'b',
    title: 'B',
    children: [
      { id: 'b1', title: 'B1' },
    ],
  },
  { id: 'c', title: 'C' },
])

describe('taskTree helpers', () => {
  it('flattens tree nodes with depth and parent id', () => {
    expect(tree.map((row) => [row.id, row._depth, row._parentId || null])).toEqual([
      ['a', 0, null],
      ['a1', 1, 'a'],
      ['a2', 1, 'a'],
      ['b', 0, null],
      ['b1', 1, 'b'],
      ['c', 0, null],
    ])
  })

  it('detects child tasks and hides descendants of collapsed tasks', () => {
    expect(hasTaskChildren(tree, 'a')).toBe(true)
    expect(hasTaskChildren(tree, 'c')).toBe(false)
    expect(ids(getVisibleTaskRows(tree, new Set(['a'])))).toEqual(['a', 'b', 'b1', 'c'])
  })

  it('moves a visible parent task while keeping hidden descendants in the full tree', () => {
    const visible = getVisibleTaskRows(tree, new Set(['a']))
    const movedVisible = moveVisibleRow(visible, 0, 2)
    const moved = movedVisible.find((row) => row.id === 'a')

    expect(moved).toBeTruthy()
    const siblings = orderedSiblingsForTask(movedVisible, moved!)
    const normalized = normalizeTaskTreeForScope(tree, moved!, siblings)

    expect(ids(normalized)).toEqual(['b', 'b1', 'a', 'a1', 'a2', 'c'])
  })

  it('reorders sibling subtasks without moving them outside the parent task', () => {
    const movedVisible = moveVisibleRow(tree, 2, 1)
    const moved = movedVisible.find((row) => row.id === 'a2')

    expect(moved).toBeTruthy()
    const siblings = orderedSiblingsForTask(movedVisible, moved!)
    const normalized = normalizeTaskTreeForScope(tree, moved!, siblings)

    expect(ids(normalized)).toEqual(['a', 'a2', 'a1', 'b', 'b1', 'c'])
  })
})

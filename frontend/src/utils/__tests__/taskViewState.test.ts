import { describe, expect, it } from 'vitest'
import { defaultTaskListState, parseTaskListState, safeTaskReturnPath, taskViewKey } from '../taskViewState'

describe('task view continuity', () => {
  it('restores a filtered later page with global deadline sorting and scroll position', () => {
    const state = { ...defaultTaskListState, page: 3, status: 'in_progress', assignee: 'person-id', sortBy: 'deadline', sortOrder: 'asc', scrollTop: 420 }
    expect(parseTaskListState(JSON.stringify(state))).toEqual(state)
    expect(taskViewKey('alice', 'one')).not.toBe(taskViewKey('bob', 'one'))
    expect(taskViewKey('alice', 'one')).not.toBe(taskViewKey('alice', 'two'))
  })
  it('handles damaged and stale browser state without invalid request arguments', () => {
    expect(parseTaskListState('{')).toEqual(defaultTaskListState)
    expect(parseTaskListState('null')).toEqual(defaultTaskListState)
    expect(parseTaskListState(JSON.stringify({ page: -1, pageSize: 9999, status: 'deleted', sortBy: 'sql', scrollTop: -10 }))).toEqual(defaultTaskListState)
  })
  it('accepts local source links while refusing external or malformed return paths', () => {
    expect(safeTaskReturnPath('/projects/p/tasks?page=2')).toBe('/projects/p/tasks?page=2')
    for (const path of ['//outside.test', 'https://outside.test', '/projects\\outside', '/projects\nfoo', '/login', ['dashboard']]) {
      expect(safeTaskReturnPath(path)).toBeNull()
    }
  })
})

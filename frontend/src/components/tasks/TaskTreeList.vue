<script setup lang="ts">
import { computed, ref } from 'vue'
import { useVirtualList } from '@vueuse/core'
import draggable from 'vuedraggable'
import type { FlatTaskRow } from '@/utils/taskTree'

const props = defineProps<{
  rows: FlatTaskRow[]
  canEdit: boolean
  move: (event: any) => boolean
}>()
const emit = defineEmits<{
  start: [event: any]
  end: [event: any]
  scroll: []
}>()
const virtualized = computed(() => props.rows.length > 100)
const draggedId = ref<string | null>(null)
const { list, containerProps } = useVirtualList(computed(() => props.rows), { itemHeight: 44, overscan: 8 })
const { onScroll: updateRange, ...viewportProps } = containerProps
const renderedIds = computed(() => new Set(list.value.map(({ data }) => data.id)))

function onScroll(event: Event) {
  const container = event.currentTarget as HTMLElement
  const maxScrollTop = Math.max(0, props.rows.length * 44 - container.clientHeight)
  if (container.scrollTop > maxScrollTop) container.scrollTop = maxScrollTop
  updateRange()
  emit('scroll')
}

function onDragChoose(event: any) {
  draggedId.value = props.rows[event.oldIndex]?.id || null
}

function onDragStart(event: any) {
  onDragChoose(event)
  emit('start', event)
}

function onDragEnd(event: any) {
  emit('end', event)
  draggedId.value = null
}
</script>

<template>
  <div v-bind="viewportProps" class="task-list-viewport" :class="{ virtualized }" @scroll="onScroll">
    <!-- Keep lightweight row elements so Sortable retains full-tree indices and auto-scroll. -->
    <draggable
      :model-value="rows" item-key="id" tag="div" class="task-drag-list"
      ghost-class="ghost-row" handle=".task-drag-handle" :animation="160"
      :disabled="!canEdit" :move="move" @choose="onDragChoose" @unchoose="draggedId = null"
      @start="onDragStart" @end="onDragEnd"
    >
      <template #item="{ element: task }">
        <div class="task-row-slot">
          <slot :task="task" :virtualized="virtualized" :visible="!virtualized || renderedIds.has(task.id) || draggedId === task.id" />
        </div>
      </template>
    </draggable>
  </div>
</template>

<style scoped>
.task-list-viewport.virtualized { height: min(560px, 65vh); }
.ghost-row { opacity: 0.48; background: #ecf5ff; }
</style>

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getActors, deleteActor, deleteAllActors, updateActor, importActorsFromOverrideBg } from '@/api/actors'
import type { ActorItem } from '@/api/actors'

export const useActorStore = defineStore('actor', () => {
  const actors = ref<ActorItem[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(50)
  const search = ref('')
  const duplicateType = ref('all')
  const loading = ref(false)
  const error = ref<string | null>(null)
  const hasMore = computed(() => actors.value.length < total.value)

  async function fetchActors(reset = false) {
    if (reset) { page.value = 1; actors.value = [] }
    loading.value = true; error.value = null
    try {
      const data = await getActors({
        search: search.value || undefined,
        duplicate_type: duplicateType.value === 'all' ? undefined : duplicateType.value,
        page: page.value, page_size: pageSize.value,
      })
      if (reset) { actors.value = data.items } else { actors.value.push(...data.items) }
      total.value = data.total
    } catch (e: any) { error.value = e.message || '获取演员列表失败' }
    finally { loading.value = false }
  }

  async function loadMore() {
    if (loading.value || !hasMore.value) return
    page.value += 1
    await fetchActors(false)
  }

  async function removeActor(id: number) {
    try { await deleteActor(id); actors.value = actors.value.filter(a => a.id !== id); total.value -= 1; return true }
    catch (e: any) { error.value = e.message || '删除演员失败'; return false }
  }

  async function removeAll() {
    try { await deleteAllActors(); actors.value = []; total.value = 0; page.value = 1; return true }
    catch (e: any) { error.value = e.message || '清空演员库失败'; return false }
  }

  async function updateActorInfo(id: number, data: Partial<ActorItem>) {
    try {
      if (data.duplicate_tmdb_id) {
        const matches = data.duplicate_tmdb_id.match(/\d+/g)
        data.duplicate_tmdb_id = matches ? Array.from(new Set(matches)).join(',') : ''
      }
      const updatedActor = await updateActor(id, data)
      const index = actors.value.findIndex(a => a.id === id)
      if (index !== -1) actors.value[index] = { ...actors.value[index], ...updatedActor }
      return true
    } catch (e: any) { error.value = e.message || '更新演员失败'; return false }
  }

  async function importFromOverrideBg() {
    try { const res = await importActorsFromOverrideBg(); return res.success }
    catch (e: any) { error.value = e.message || '提交后台导入任务失败'; return false }
  }

  return {
    actors, total, page, pageSize, search, duplicateType, loading, error, hasMore,
    fetchActors, loadMore, removeActor, updateActorInfo, removeAll, importFromOverrideBg,
  }
})

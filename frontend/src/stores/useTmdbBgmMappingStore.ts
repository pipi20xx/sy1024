import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getMappingsApi, exportMappingsApi, importDiffApi, applyImportApi,
  updateMappingApi, deleteMappingApi, clearAllMappingsApi,
  type TmdbBgmMappingItem, type DiffItem, type ImportDiffResponse, type TmdbBgmMappingUpdate,
} from '@/api/tmdbBgmMapping'
import { api } from '@/api/client'

interface TmdbItemInfo {
  id: string
  type: 'tmdb-tv' | 'tmdb-movies2'
  source: string
  full_metadata: {
    name?: string; title?: string; original_name?: string; original_title?: string
    first_air_date?: string; release_date?: string; poster_path?: string
  }
  images: Array<{ label: string; url: string; name: string }>
  seasons?: Array<{ season_number: number; metadata: { name?: string; air_date?: string }; episodes?: Array<{ episode_number: number }> }>
}

export const useTmdbBgmMappingStore = defineStore('tmdbBgmMapping', () => {
  const mappings = ref<TmdbBgmMappingItem[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(60)
  const search = ref('')
  const tmdbType = ref('all')
  const tmdbItems = ref<Map<string, TmdbItemInfo>>(new Map())
  const isLoading = ref(false)
  const diffResult = ref<ImportDiffResponse | null>(null)
  const isImporting = ref(false)
  const hasMore = computed(() => mappings.value.length < total.value)

  async function loadMappings(reset = false) {
    if (reset) { page.value = 1; mappings.value = [] }
    isLoading.value = true
    try {
      const result = await getMappingsApi({
        search: search.value || undefined,
        tmdb_type: tmdbType.value !== 'all' ? tmdbType.value : undefined,
        page: page.value,
        page_size: pageSize.value,
      })
      if (reset) { mappings.value = result.items }
      else { mappings.value.push(...result.items) }
      total.value = result.total
    } catch (err) { console.error('Failed to load mappings:', err) }
    finally { isLoading.value = false }
  }

  async function loadMore() {
    if (isLoading.value || !hasMore.value) return
    page.value += 1
    await loadMappings(false)
  }

  async function loadTmdbItem(tmdbId: number, tmdbType: 'tv' | 'movie') {
    const itemType = tmdbType === 'tv' ? 'tmdb-tv' : 'tmdb-movies2'
    const key = `${itemType}:${tmdbId}`
    if (tmdbItems.value.has(key)) return
    try {
      const item = await api.get<TmdbItemInfo>(`/api/items/${itemType}/${tmdbId}/details`)
      if (item) tmdbItems.value.set(key, item)
    } catch (err) { console.error(`Failed to load TMDB item ${key}:`, err) }
  }

  function getTmdbItem(tmdbId: number, tmdbType: 'tv' | 'movie'): TmdbItemInfo | undefined {
    const itemType = tmdbType === 'tv' ? 'tmdb-tv' : 'tmdb-movies2'
    return tmdbItems.value.get(`${itemType}:${tmdbId}`)
  }

  async function exportMappings() {
    try {
      const data = await exportMappingsApi()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `tmdb_bgm_mapping_${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(a); a.click(); document.body.removeChild(a)
      URL.revokeObjectURL(url); return true
    } catch (err) { console.error('Failed to export mappings:', err); return false }
  }

  async function importAndDiff(importData: TmdbBgmMappingItem[]) {
    isImporting.value = true
    try { diffResult.value = await importDiffApi(importData); return true }
    catch (err: any) { console.error('Failed to import and diff:', err); return false }
    finally { isImporting.value = false }
  }

  async function applyImport(selectedDiffItems: DiffItem[]) {
    isImporting.value = true
    try { await applyImportApi(selectedDiffItems); await loadMappings(true); diffResult.value = null; return true }
    catch (err) { console.error('Failed to apply import:', err); return false }
    finally { isImporting.value = false }
  }

  async function updateMapping(update: TmdbBgmMappingUpdate) {
    isLoading.value = true
    try { await updateMappingApi(update); await loadMappings(true); return true }
    catch (err: any) { console.error('Failed to update mapping:', err); return false }
    finally { isLoading.value = false }
  }

  async function deleteMapping(tmdbId: number, tmdbType: string) {
    isLoading.value = true
    try { await deleteMappingApi(tmdbId, tmdbType); await loadMappings(true); return true }
    catch (err) { console.error('Failed to delete mapping:', err); return false }
    finally { isLoading.value = false }
  }

  async function clearAllMappings() {
    isLoading.value = true
    try { await clearAllMappingsApi(); mappings.value = []; total.value = 0; return true }
    catch (err) { console.error('Failed to clear all mappings:', err); return false }
    finally { isLoading.value = false }
  }

  function clearDiffResult() { diffResult.value = null }

  return {
    mappings, total, page, pageSize, search, tmdbType,
    tmdbItems, isLoading, diffResult, isImporting, hasMore,
    loadMappings, loadMore, loadTmdbItem, getTmdbItem, exportMappings,
    importAndDiff, applyImport, updateMapping, deleteMapping, clearAllMappings, clearDiffResult,
  }
})

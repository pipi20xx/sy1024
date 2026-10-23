import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getItems, getGenres, getYears } from '@/api/items'
import type { ItemSummary, ItemType } from '@/types'

export const useItemStore = defineStore('item', () => {
  const items = ref<ItemSummary[]>([])
  const total = ref(0)
  const currentPage = ref(1)
  const limit = ref(50)
  const hasNextPage = ref(false)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const currentItemType = ref<ItemType>('tmdb-tv')

  // 筛选器
  const searchTerm = ref('')
  const selectedSource = ref<string | null>(null)
  const selectedPosterStatus = ref<string | null>(null)
  const selectedGenre = ref<string | null>(null)
  const selectedYear = ref<string | null>(null)
  const selectedMonth = ref<string | null>(null)
  const sortBy = ref<string>('date_desc')

  // 可用筛选选项
  const availableGenres = ref<string[]>([])
  const availableYears = ref<string[]>([])

  // 请求计数器：防止过期响应覆盖最新结果
  let loadRequestId = 0

  // 待处理的入库状态：WS 消息可能在 items push 之前到达，先暂存，push 后再应用
  let _pendingLibraryStatuses: Record<string, boolean> | null = null

  async function loadItems(type: ItemType, page = 1) {
    const requestId = ++loadRequestId
    isLoading.value = true
    error.value = null

    try {
      const response = await getItems({
        item_type: type,
        page,
        limit: limit.value,
        search_term: searchTerm.value || undefined,
        source: selectedSource.value as any,
        poster_status: selectedPosterStatus.value as any,
        genres: selectedGenre.value ? [selectedGenre.value] : undefined,
        year: selectedYear.value || undefined,
        month: selectedMonth.value ? String(selectedMonth.value) : undefined,
        sort_by: sortBy.value,
      })

      // 丢弃过期响应（例如筛选条件已变更但旧请求仍在进行中）
      if (requestId !== loadRequestId) return

      if (page === 1) {
        items.value = response.items
      } else {
        items.value.push(...response.items)
      }

      // 应用暂存的入库状态（WS 可能在 push 之前就已到达）
      if (_pendingLibraryStatuses) {
        _applyLibraryStatus(_pendingLibraryStatuses)
        _pendingLibraryStatuses = null
      }

      total.value = response.total_items
      currentPage.value = page
      hasNextPage.value = response.has_more
      currentItemType.value = type
    } catch (err: any) {
      if (requestId === loadRequestId) {
        error.value = err.message || '加载项目失败'
      }
    } finally {
      if (requestId === loadRequestId) {
        isLoading.value = false
      }
    }
  }

  function loadMoreItems() {
    if (hasNextPage.value && !isLoading.value) {
      loadItems(currentItemType.value, currentPage.value + 1)
    }
  }

  function setCurrentItemType(type: ItemType | string) {
    const t = type as ItemType
    if (currentItemType.value !== t) {
      currentItemType.value = t
      resetFilters(false)
      currentPage.value = 1
      items.value = []
      loadItems(t)
      loadAvailableFilters(t)
    }
  }

  async function loadAvailableFilters(type: ItemType) {
    try {
      const [genres, years] = await Promise.all([getGenres(type), getYears(type)])
      availableGenres.value = genres
      availableYears.value = years
    } catch (err) {
      console.error('Failed to load filters:', err)
    }
  }

  function applyFilters() {
    currentPage.value = 1
    items.value = []
    loadItems(currentItemType.value)
  }

  function resetFilters(reload = true) {
    searchTerm.value = ''
    selectedSource.value = null
    selectedPosterStatus.value = null
    selectedGenre.value = null
    selectedYear.value = null
    selectedMonth.value = null
    sortBy.value = 'date_desc'
    if (reload) applyFilters()
  }

  /**
   * 实际执行入库状态更新逻辑。
   * 遍历 statuses，更新 items 中能匹配到的项，返回未匹配的项。
   */
  function _applyLibraryStatus(statuses: Record<string, boolean>): Record<string, boolean> {
    const idToIndex = new Map<string, number>()
    items.value.forEach((item, index) => {
      idToIndex.set(item.id, index)
    })

    const unmatched: Record<string, boolean> = {}
    for (const [tmdbId, inLibrary] of Object.entries(statuses)) {
      const index = idToIndex.get(tmdbId)
      if (index !== undefined) {
        items.value[index] = { ...items.value[index], in_library: inLibrary }
      } else {
        unmatched[tmdbId] = inLibrary
      }
    }
    return unmatched
  }

  /**
   * 异步更新 items 的 in_library 字段（由 WebSocket 推送触发）。
   * 如果 WS 消息在 items push 之前到达（如分页加载时），会暂存状态，
   * 等 loadItems push 完成后再自动应用。
   */
  function updateLibraryStatus(itemType: string, statuses: Record<string, boolean>) {
    // 仅当 WS 推送的类型与当前列表类型一致时才处理
    if (itemType !== currentItemType.value) return

    const unmatched = _applyLibraryStatus(statuses)

    // 如果有未匹配的项，说明 WS 消息比 loadItems push 先到达，暂存等待 push 后再应用
    if (Object.keys(unmatched).length > 0) {
      _pendingLibraryStatuses = { ...(_pendingLibraryStatuses || {}), ...unmatched }
    }
  }

  return {
    items, total, currentPage, limit, hasNextPage, isLoading, error, currentItemType,
    searchTerm, selectedSource, selectedPosterStatus, selectedGenre, selectedYear, selectedMonth, sortBy,
    availableGenres, availableYears,
    loadItems, loadMoreItems, setCurrentItemType, loadAvailableFilters, applyFilters, resetFilters,
    updateLibraryStatus,
  }
})

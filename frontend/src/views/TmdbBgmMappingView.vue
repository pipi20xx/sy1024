<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, onDeactivated } from 'vue'
import { useRouter } from 'vue-router'
import { useTmdbBgmMappingStore, useUiStore } from '@/stores'
defineOptions({ name: 'TmdbBgmMappingView' })
import {
  updateMappingApi,
  type TmdbBgmMappingItem,
  type TmdbBgmMappingUpdate,
  type DiffItem,
} from '@/api/tmdbBgmMapping'
import { useNotification, useConfirm, useInfiniteScroll } from '@/composables'

const store = useTmdbBgmMappingStore()
const uiStore = useUiStore()
const router = useRouter()
const { notify } = useNotification()
const { confirm } = useConfirm()

const searchQuery = ref('')

// 类型筛选
const typeFilterOptions = [
  { title: '全部', value: 'all' },
  { title: '剧集 (tv)', value: 'tv' },
  { title: '电影 (movie)', value: 'movie' },
]

// 无限滚动
useInfiniteScroll({
  onLoad: () => store.loadMore(),
  hasMore: () => store.hasMore,
  isLoading: () => store.isLoading,
})

// 添加映射弹框
const showAddDialog = ref(false)
const addForm = ref<{
  tmdb_id: string
  tmdb_type: 'tv' | 'movie'
  season_mappings: Record<string, number[]>
  season_number: number
  bgm_ids: string
}>({
  tmdb_id: '',
  tmdb_type: 'tv',
  season_mappings: {},
  season_number: 1,
  bgm_ids: '',
})

// 导入
const showImportDialog = ref(false)
const importFileInput = ref<HTMLInputElement | null>(null)

function triggerImportFile() {
  importFileInput.value?.click()
}

// 搜索
let searchTimer: ReturnType<typeof setTimeout> | null = null

function handleSearch() {
  store.search = searchQuery.value
  loadedItems.value.clear()
  store.loadMappings(true)
}

function handleSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(handleSearch, 400)
}

function handleTypeFilterChange() {
  loadedItems.value.clear()
  store.loadMappings(true)
}

onMounted(() => {
  store.loadMappings(true)
})

// ── 卡片点击 → 跳转独立详情页 ──
function handleCardClick(item: TmdbBgmMappingItem) {
  router.push({ name: 'tmdbBgmMappingDetail', params: { tmdbId: String(item.tmdb_id), tmdbType: item.tmdb_type } })
}

// ── 获取卡片展示信息 ──
function getTmdbTitle(item: TmdbBgmMappingItem): string {
  const tmdbItem = store.getTmdbItem(item.tmdb_id, item.tmdb_type)
  if (tmdbItem?.full_metadata) {
    return tmdbItem.full_metadata.name || tmdbItem.full_metadata.title || `TMDB ${item.tmdb_id}`
  }
  return `TMDB ${item.tmdb_id}`
}

function getTmdbYear(item: TmdbBgmMappingItem): string {
  const tmdbItem = store.getTmdbItem(item.tmdb_id, item.tmdb_type)
  if (tmdbItem?.full_metadata) {
    const date = tmdbItem.full_metadata.first_air_date || tmdbItem.full_metadata.release_date
    if (date) return `(${date.split('-')[0]})`
  }
  return ''
}

function getTmdbPoster(item: TmdbBgmMappingItem): string {
  const tmdbItem = store.getTmdbItem(item.tmdb_id, item.tmdb_type)
  if (tmdbItem?.images) {
    const poster = tmdbItem.images.find((img: any) => img.label === '海报 (Poster)')
    if (poster) return poster.url
  }
  return '/static/placeholder.png'
}

function getBgmCount(item: TmdbBgmMappingItem): number {
  return Object.values(item.season_mappings || {}).flat().length
}

// ── IntersectionObserver 懒加载卡片 TMDB 数据 ──
const loadedItems = ref<Set<string>>(new Set())
const observerMap = ref<Map<string, IntersectionObserver>>(new Map())

function setupCardObserver(el: HTMLElement, item: TmdbBgmMappingItem) {
  const key = `${item.tmdb_type}:${item.tmdb_id}`
  if (observerMap.value.has(key)) return

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting && !loadedItems.value.has(key)) {
          loadedItems.value.add(key)
          store.loadTmdbItem(item.tmdb_id, item.tmdb_type)
          observer.disconnect()
          observerMap.value.delete(key)
        }
      })
    },
    { rootMargin: '300px', threshold: 0.01 }
  )
  observer.observe(el)
  observerMap.value.set(key, observer)
}

function handleCardMounted(el: any, item: TmdbBgmMappingItem) {
  if (el?.$el) setupCardObserver(el.$el as HTMLElement, item)
  else if (el instanceof HTMLElement) setupCardObserver(el, item)
}

onUnmounted(() => {
  observerMap.value.forEach(o => o.disconnect())
  observerMap.value.clear()
  loadedItems.value.clear()
  if (searchTimer) { clearTimeout(searchTimer); searchTimer = null }
})

// keep-alive: 停用时断开观察器释放资源
onDeactivated(() => {
  observerMap.value.forEach(o => o.disconnect())
})

// ── 导出 ──
async function handleExport() {
  const success = await store.exportMappings()
  if (success) notify('导出成功', '', 'success')
  else notify('导出失败', '', 'error')
}

// ── 导入文件 ──
async function handleImportFile(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) return
  try {
    const text = await target.files[0].text()
    const data = JSON.parse(text)
    const importData = Array.isArray(data) ? data : data.items || []
    const success = await store.importAndDiff(importData)
    if (success) {
      showImportDialog.value = true
      selectedDiffKeys.value.clear()
      store.diffResult?.diff_items.forEach((item: any) => {
        if (item.diff_type !== 'unchanged') selectedDiffKeys.value.add(getDiffKey(item))
      })
      notify('导入对比完成', '', 'info')
    }
  } catch (e: any) {
    notify('导入失败', e.message, 'error')
  }
  target.value = ''
}

// ── 导入对比 ──
const selectedDiffKeys = ref<Set<string>>(new Set())
const filterType = ref<string>('all')

const filteredDiffItems = computed(() => {
  if (!store.diffResult) return []
  if (filterType.value === 'all') return store.diffResult.diff_items
  return store.diffResult.diff_items.filter((item: any) => item.diff_type === filterType.value)
})

const selectedCount = computed(() => selectedDiffKeys.value.size)

function getDiffKey(item: DiffItem): string {
  return `${item.tmdb_id}-${item.tmdb_type}-${item.season_number}`
}

function toggleDiffItem(item: DiffItem) {
  const key = getDiffKey(item)
  if (selectedDiffKeys.value.has(key)) selectedDiffKeys.value.delete(key)
  else selectedDiffKeys.value.add(key)
}

function selectAll() {
  store.diffResult?.diff_items.forEach((item: any) => selectedDiffKeys.value.add(getDiffKey(item)))
}

function selectCurrent() {
  filteredDiffItems.value.forEach((item: any) => selectedDiffKeys.value.add(getDiffKey(item)))
}

function deselectAll() {
  selectedDiffKeys.value.clear()
}

const diffTypeMap: Record<string, { text: string; color: string }> = {
  new: { text: '新增', color: 'success' },
  modified: { text: '修改', color: 'warning' },
  deleted: { text: '删除', color: 'error' },
  unchanged: { text: '未变更', color: 'default' },
}

async function handleApplyImport() {
  if (selectedCount.value === 0) return
  const selectedItems = store.diffResult?.diff_items.filter((item: any) =>
    selectedDiffKeys.value.has(getDiffKey(item))
  ) || []
  const ok = await confirm({
    title: '应用导入',
    content: `将应用 ${selectedItems.length} 条变更`,
  })
  if (!ok) return
  const success = await store.applyImport(selectedItems)
  if (success) {
    showImportDialog.value = false
    selectedDiffKeys.value.clear()
    notify('导入已应用', '', 'success')
  }
}

// ── 清空 ──
async function handleClearAll() {
  const ok = await confirm({
    title: '清空所有映射',
    content: `确认删除全部 ${store.mappings.length} 条映射？此操作不可恢复！`,
    confirmColor: 'error',
  })
  if (!ok) return
  const success = await store.clearAllMappings()
  if (success) notify('已清空', '', 'success')
}

// ── 删除单个映射 ──
async function handleDeleteMapping(tmdbId: number, tmdbType: string) {
  const ok = await confirm({
    title: '删除映射',
    content: `确认删除 TMDB ID ${tmdbId} (${tmdbType}) 的映射？`,
    confirmColor: 'error',
  })
  if (!ok) return
  const success = await store.deleteMapping(tmdbId, tmdbType)
  if (success) notify('已删除', '', 'success')
}

// ── 添加映射 ──
function handleAddSeason() {
  const bgmIdList = addForm.value.bgm_ids
    .replace(/，/g, ',')
    .split(',')
    .map(id => parseInt(id.trim()))
    .filter(id => !isNaN(id))

  if (bgmIdList.length === 0) {
    notify('请输入至少一个 BGM ID', '', 'warning')
    return
  }
  const seasonKey = addForm.value.season_number.toString()
  addForm.value.season_mappings[seasonKey] = bgmIdList
  addForm.value.season_number++
  addForm.value.bgm_ids = ''
}

function handleRemoveSeasonFromAdd(seasonKey: string) {
  delete addForm.value.season_mappings[seasonKey]
}

async function handleSaveAdd() {
  if (!addForm.value.tmdb_id.trim()) {
    notify('请输入 TMDB ID', '', 'warning')
    return
  }
  if (Object.keys(addForm.value.season_mappings).length === 0) {
    notify('请至少添加一个季数映射', '', 'warning')
    return
  }

  const update: TmdbBgmMappingUpdate = {
    tmdb_id: parseInt(addForm.value.tmdb_id),
    tmdb_type: addForm.value.tmdb_type,
    season_mappings: addForm.value.season_mappings,
  }

  try {
    await updateMappingApi(update)
    notify('添加成功', '', 'success')
    showAddDialog.value = false
    addForm.value = { tmdb_id: '', tmdb_type: 'tv', season_mappings: {}, season_number: 1, bgm_ids: '' }
    await store.loadMappings(true)
  } catch (e: any) {
    notify('添加失败', e.message, 'error')
  }
}

</script>

<template>
  <v-container fluid class="pa-6">
    <!-- 页头 -->
    <div class="d-flex flex-wrap align-center mb-4 ga-3">
      <div class="flex-grow-1">
        <h1 class="text-h5 font-weight-bold">TMDB-BGM 映射</h1>
        <p class="text-caption text-medium-emphasis mt-1">
          管理 TMDB 条目与 Bangumi 的关联映射，共 {{ store.total }} 条
        </p>
      </div>
      <div class="d-flex ga-2 flex-wrap">
        <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-plus" @click="showAddDialog = true">添加映射</v-btn>
        <v-btn size="small" color="info" variant="tonal" prepend-icon="mdi-refresh" @click="loadedItems.clear(); store.loadMappings(true)">刷新</v-btn>
        <v-btn size="small" color="info" variant="tonal" prepend-icon="mdi-export" @click="handleExport">导出</v-btn>
        <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-upload" @click="triggerImportFile">导入</v-btn>
        <input ref="importFileInput" type="file" accept=".json" @change="handleImportFile" class="d-none" />
        <v-btn size="small" variant="tonal" color="error" prepend-icon="mdi-delete-sweep" @click="handleClearAll">清空</v-btn>
      </div>
    </div>

    <!-- 优先级提示 -->
    <v-alert type="info" variant="tonal" density="compact" class="mb-4">
      本映射表为手动映射表，具有最高优先级。当 TMDB ID 存在于本表时，系统将优先使用本表中的 Bangumi ID。
    </v-alert>

    <!-- 搜索 + 筛选 -->
    <div class="d-flex ga-3 mb-4 align-center flex-wrap">
      <v-text-field
        v-model="searchQuery"
        placeholder="搜索 TMDB ID / BGM ID..."
        density="compact"
        variant="outlined"
        prepend-inner-icon="mdi-magnify"
        clearable
        hide-details
        class="filter-field"
        @input="handleSearchInput"
        @click:clear="searchQuery = ''; handleSearch()"
      />
      <v-select
        v-model="store.tmdbType"
        :items="typeFilterOptions"
        density="compact"
        variant="outlined"
        hide-details
        class="mw-160px"
        @update:model-value="handleTypeFilterChange"
      />
      <span class="text-caption text-medium-emphasis">{{ store.mappings.length }} / {{ store.total }}</span>
    </div>

    <!-- 加载中 -->
    <div v-if="store.isLoading && !store.mappings.length" class="text-center pa-8">
      <v-progress-circular indeterminate color="primary" size="40" />
      <p class="mt-3 text-medium-emphasis">加载中...</p>
    </div>

    <!-- 映射卡片网格 - 与首页一致 -->
    <v-row v-else-if="store.mappings.length">
      <v-col v-for="m in store.mappings" :key="`${m.tmdb_id}-${m.tmdb_type}`" v-bind="uiStore.gridColProps">
        <v-card
          :ref="(el: any) => handleCardMounted(el, m)"
          rounded="xl"
          hover
          variant="outlined"
          class="h-100 cursor-pointer"
          @click="handleCardClick(m)"
        >
          <!-- 海报 -->
          <v-img
            :src="getTmdbPoster(m)"
            aspect-ratio="2/3"
            cover
            class="poster-rounded"
          >
            <template #error>
              <div class="d-flex align-center justify-center fill-height bg-surface-variant">
                <v-icon size="48" color="grey-lighten-1">mdi-link-variant</v-icon>
              </div>
            </template>
            <!-- 类型标签 -->
            <v-chip
              :color="m.tmdb_type === 'movie' ? 'info' : 'success'"
              size="x-small"
              variant="flat"
              density="compact"
              class="poster-badge position-absolute corner-badge corner-badge--tl"
            >
              {{ m.tmdb_type === 'movie' ? '电影' : '剧集' }}
            </v-chip>
            <!-- BGM 数量 -->
            <v-chip
              v-if="getBgmCount(m) > 0"
              size="x-small"
              variant="flat"
              :color="getBgmCount(m) > 0 ? 'info' : 'grey'"
              density="compact"
              class="poster-badge position-absolute corner-badge corner-badge--tr"
            >
              <v-icon start size="x-small">mdi-link-variant</v-icon>
              {{ getBgmCount(m) }} BGM
            </v-chip>
          </v-img>

          <!-- 底部信息 -->
          <v-card-text class="pa-3 text-center">
            <div class="text-body-2 font-weight-bold text-truncate" :title="getTmdbTitle(m)">{{ getTmdbTitle(m) }}</div>
            <div class="text-caption text-medium-emphasis mt-1">
              {{ getTmdbYear(m) }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- 加载更多提示 -->
    <div v-if="store.isLoading && store.mappings.length" class="text-center pa-4">
      <v-progress-circular indeterminate size="24" color="primary" />
      <span class="ml-2 text-caption text-medium-emphasis">加载中...</span>
    </div>
    <div v-else-if="!store.hasMore && store.mappings.length" class="text-center pa-2 text-caption text-medium-emphasis">
      已全部加载 ({{ store.mappings.length }} / {{ store.total }})
    </div>

    <!-- 空状态 -->
    <v-card v-if="!store.isLoading && !store.mappings.length" variant="outlined" rounded="xl" class="pa-8">
      <div class="text-center">
        <v-icon size="64" color="grey-lighten-1">mdi-link-off</v-icon>
        <div class="text-h6 mt-3 mb-2">{{ store.search ? '未找到匹配的映射' : '暂无映射数据' }}</div>
        <div class="text-caption text-medium-emphasis mb-4">
          {{ store.search ? '尝试更换关键词' : '通过「添加映射」手动创建或「导入文件」批量导入' }}
        </div>
        <v-btn v-if="!searchQuery" color="primary" variant="tonal" prepend-icon="mdi-plus" @click="showAddDialog = true">
          添加第一个映射
        </v-btn>
      </div>
    </v-card>

    <!-- ═══════════════════════════════════════════ -->
    <!-- 添加映射弹框 -->
    <!-- ═══════════════════════════════════════════ -->
    <v-dialog v-model="showAddDialog" max-width="520" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-plus" class="mr-2" />
          添加映射
          <v-spacer />
          <v-btn size="small" variant="text" icon="mdi-close" @click="showAddDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-row density="compact">
            <v-col cols="5">
              <v-select v-model="addForm.tmdb_type" :items="[
                { title: '剧集 (tv)', value: 'tv' },
                { title: '电影 (movie)', value: 'movie' },
              ]" label="TMDB 类型" density="compact" variant="outlined" />
            </v-col>
            <v-col cols="7">
              <v-text-field v-model="addForm.tmdb_id" label="TMDB ID" density="compact" variant="outlined"
                placeholder="数字 ID" />
            </v-col>
          </v-row>

          <!-- 已添加的季映射 -->
          <div v-if="Object.keys(addForm.season_mappings).length" class="mb-3">
            <div class="text-caption font-weight-bold text-medium-emphasis mb-1">已添加映射</div>
            <div v-for="(bgmIds, seasonKey) in addForm.season_mappings" :key="seasonKey"
              class="d-flex align-center ga-2 mb-1"
            >
              <v-chip size="x-small" variant="tonal" label color="success">S{{ seasonKey }}</v-chip>
              <span class="text-caption">{{ bgmIds.join(', ') }}</span>
              <v-btn size="small" variant="tonal" icon="mdi-close" density="compact" color="error"
                @click="handleRemoveSeasonFromAdd(seasonKey as string)" />
            </div>
          </div>

          <v-row density="compact">
            <v-col cols="4">
              <v-text-field v-model.number="addForm.season_number" label="季号" type="number" density="compact"
                variant="outlined" />
            </v-col>
            <v-col cols="8">
              <v-text-field v-model="addForm.bgm_ids" label="BGM ID (逗号分隔)" density="compact" variant="outlined"
                placeholder="12345, 67890" @keyup.enter="handleAddSeason" />
            </v-col>
          </v-row>
          <v-btn size="small" color="primary" variant="tonal" block @click="handleAddSeason" class="mb-2">添加此季映射</v-btn>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showAddDialog = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="handleSaveAdd">添加</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ═══════════════════════════════════════════ -->
    <!-- 导入结果对话框 -->
    <!-- ═══════════════════════════════════════════ -->
    <v-dialog v-model="showImportDialog" max-width="1100" width="95vw" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-file-compare" class="mr-2" />
          导入对比结果
          <v-spacer />
          <v-btn size="small" variant="text" icon="mdi-close" @click="showImportDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text v-if="store.diffResult" class="pt-4">
          <!-- 统计 -->
          <div class="d-flex ga-3 mb-4">
            <v-chip size="small" variant="tonal" color="success" label>新增 {{ store.diffResult.stats?.new || 0 }}</v-chip>
            <v-chip size="small" variant="tonal" color="warning" label>修改 {{ store.diffResult.stats?.modified || 0 }}</v-chip>
            <v-chip size="small" variant="tonal" color="error" label>删除 {{ store.diffResult.stats?.deleted || 0 }}</v-chip>
            <v-chip size="small" variant="tonal" label>未变更 {{ store.diffResult.stats?.unchanged || 0 }}</v-chip>
          </div>

          <!-- 筛选 + 批量操作 -->
          <div class="d-flex justify-space-between align-center mb-3 flex-wrap ga-2">
            <v-btn-toggle v-model="filterType" density="compact" variant="outlined" divided>
              <v-btn value="all" size="small">全部</v-btn>
              <v-btn value="new" size="small">新增</v-btn>
              <v-btn value="modified" size="small">修改</v-btn>
              <v-btn value="deleted" size="small">删除</v-btn>
            </v-btn-toggle>
            <div class="d-flex ga-2">
              <v-btn size="small" variant="tonal" prepend-icon="mdi-check-all" @click="selectAll">全选</v-btn>
              <v-btn size="small" variant="tonal" prepend-icon="mdi-check" @click="selectCurrent">选中当前</v-btn>
              <v-btn size="small" variant="tonal" prepend-icon="mdi-close-circle-outline" @click="deselectAll">取消全选</v-btn>
            </div>
          </div>

          <!-- 对比表 -->
          <v-table v-if="filteredDiffItems.length" density="compact" class="diff-table">
            <thead>
              <tr>
                <th class="w-40px"></th>
                <th>TMDB ID</th>
                <th>类型</th>
                <th>季数</th>
                <th>旧 BGM IDs</th>
                <th>新 BGM IDs</th>
                <th>变更</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in filteredDiffItems" :key="getDiffKey(item)">
                <td>
                  <v-checkbox density="compact" hide-details color="primary"
                    :model-value="selectedDiffKeys.has(getDiffKey(item))"
                    @update:model-value="toggleDiffItem(item)" />
                </td>
                <td>{{ item.tmdb_id }}</td>
                <td>
                  <v-chip size="x-small" variant="tonal" :color="item.tmdb_type === 'tv' ? 'success' : 'info'" label>
                    {{ item.tmdb_type === 'tv' ? '剧集' : '电影' }}
                  </v-chip>
                </td>
                <td>{{ item.season_number === '0' ? '电影' : 'S' + item.season_number }}</td>
                <td><span class="text-caption text-medium-emphasis">{{ item.old_bgm_ids?.length ? item.old_bgm_ids.join(', ') : '—' }}</span></td>
                <td><span class="text-caption">{{ item.new_bgm_ids?.length ? item.new_bgm_ids.join(', ') : '—' }}</span></td>
                <td>
                  <v-chip
                    :color="diffTypeMap[item.diff_type]?.color || 'default'"
                    size="x-small" variant="tonal" label
                  >
                    {{ diffTypeMap[item.diff_type]?.text || item.diff_type }}
                  </v-chip>
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <span class="text-caption text-medium-emphasis ml-2">已选 {{ selectedCount }} 项</span>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showImportDialog = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-check"
            :disabled="selectedCount === 0" :loading="store.isImporting" @click="handleApplyImport">
            应用导入 ({{ selectedCount }})
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

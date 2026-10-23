<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
defineOptions({ name: 'TmdbBgmMappingDetailView' })
import { useTmdbBgmMappingStore } from '@/stores'
import {
  updateMappingApi,
  getBatchBangumiDetailsApi,
  type TmdbBgmMappingItem,
  type TmdbBgmMappingUpdate,
  type BangumiInfo,
} from '@/api/tmdbBgmMapping'
import { useNotification, useConfirm } from '@/composables'

const route = useRoute()
const router = useRouter()
const store = useTmdbBgmMappingStore()
const { notify } = useNotification()
const { confirm } = useConfirm()

// ── 路由参数 ──
const tmdbId = computed(() => Number(route.params.tmdbId))
const tmdbType = computed(() => route.params.tmdbType as 'tv' | 'movie')

// ── 查找当前映射项 ──
const selectedItem = computed<TmdbBgmMappingItem | null>(() =>
  store.mappings.find(m => m.tmdb_id === tmdbId.value && m.tmdb_type === tmdbType.value) || null
)

// ── TMDB 详情 ──
const detailTmdbItem = computed(() => {
  if (!selectedItem.value) return null
  return store.getTmdbItem(selectedItem.value.tmdb_id, selectedItem.value.tmdb_type)
})

// ── Bangumi 详情 ──
const detailBangumiInfos = ref<Map<number, BangumiInfo>>(new Map())
const isLoadingBangumi = ref(false)

// ── 编辑状态 ──
const editingSeasonMappings = ref<Record<string, number[]>>({})

// ── 编辑单条 BGM ID ──
const editingBgm = ref<{ seasonKey: string; index: number; value: string } | null>(null)

// ── 添加季度弹框 ──
const showAddSeasonDialog = ref(false)
const addSeasonForm = ref({
  season_number: 1,
  bgm_ids: '',
})

function openAddSeasonDialog() {
  const currentSeasons = Object.keys(editingSeasonMappings.value).map(key => parseInt(key))
  const maxSeason = currentSeasons.length > 0 ? Math.max(...currentSeasons) : 0
  addSeasonForm.value = { season_number: maxSeason + 1, bgm_ids: '' }
  showAddSeasonDialog.value = true
}

function handleConfirmAddSeason() {
  const bgmIdList = addSeasonForm.value.bgm_ids
    .replace(/，/g, ',')
    .split(',')
    .map(id => parseInt(id.trim()))
    .filter(id => !isNaN(id))

  if (bgmIdList.length === 0) {
    notify('请输入至少一个 BGM ID', '', 'warning')
    return
  }
  const seasonKey = addSeasonForm.value.season_number.toString()
  if (editingSeasonMappings.value[seasonKey]) {
    // 季号已存在，追加（去重）
    const existing = new Set(editingSeasonMappings.value[seasonKey])
    bgmIdList.forEach(id => existing.add(id))
    editingSeasonMappings.value[seasonKey] = Array.from(existing)
  } else {
    editingSeasonMappings.value[seasonKey] = bgmIdList
  }
  showAddSeasonDialog.value = false
  notify('已添加', `S${seasonKey} 已追加 ${bgmIdList.length} 个 BGM ID`, 'success')
}

// ── 标题信息 ──
function getTmdbTitle(): string {
  if (!selectedItem.value) return `TMDB ${tmdbId.value}`
  const item = detailTmdbItem.value
  if (item?.full_metadata) {
    return item.full_metadata.name || item.full_metadata.title || `TMDB ${tmdbId.value}`
  }
  return `TMDB ${tmdbId.value}`
}

function getTmdbYear(): string {
  const item = detailTmdbItem.value
  if (item?.full_metadata) {
    const date = item.full_metadata.first_air_date || item.full_metadata.release_date
    if (date) return `(${date.split('-')[0]})`
  }
  return ''
}

function getBangumiName(bgmId: number): string {
  const info = detailBangumiInfos.value.get(bgmId)
  return info?.name_cn || info?.name || `BGM ${bgmId}`
}

function getBangumiDate(bgmId: number): string {
  return detailBangumiInfos.value.get(bgmId)?.date || '-'
}

function getBangumiEps(bgmId: number): string {
  const info = detailBangumiInfos.value.get(bgmId)
  return info?.eps != null ? `${info.eps} 集` : '-'
}

// ── 加载数据 ──
async function loadData() {
  // 如果 store 还没有映射数据，先加载
  if (store.mappings.length === 0) {
    await store.loadMappings(true)
  }

  if (!selectedItem.value) {
    // 数据加载后仍然找不到，可能已被删除
    notify('未找到映射', '该映射可能已被删除，正在返回列表', 'warning')
    router.push('/tmdb-bgm-mapping')
    return
  }

  // 每次进入页面时，从 store 重新拷贝一份原始数据作为编辑基础
  // 这样未保存的修改不会污染下次访问
  editingSeasonMappings.value = JSON.parse(JSON.stringify(selectedItem.value.season_mappings))
  editingBgm.value = null
  detailBangumiInfos.value.clear()

  // 加载 TMDB 详情
  await store.loadTmdbItem(tmdbId.value, tmdbType.value)

  // 加载 Bangumi 详情
  const allBgmIds = Object.values(editingSeasonMappings.value).flat()
  if (allBgmIds.length > 0) {
    isLoadingBangumi.value = true
    try {
      const infos = await getBatchBangumiDetailsApi(allBgmIds)
      detailBangumiInfos.value.clear()
      infos.forEach(info => {
        if (info.id) detailBangumiInfos.value.set(info.id, info)
      })
    } catch (err) {
      console.error('加载 Bangumi 详情失败:', err)
    } finally {
      isLoadingBangumi.value = false
    }
  }
}

onMounted(() => {
  loadData()
})

// keep-alive: 每次激活时重新加载编辑数据（丢弃未保存的修改）
// 通过 watch route.params 变化来判断是否切换了不同的映射
watch(
  () => [route.params.tmdbId, route.params.tmdbType],
  () => {
    if (route.name === 'tmdbBgmMappingDetail') {
      loadData()
    }
  }
)

// ── 单条 BGM ID 编辑 ──
function handleEditBgm(seasonKey: string, index: number) {
  editingBgm.value = {
    seasonKey,
    index,
    value: String(editingSeasonMappings.value[seasonKey]?.[index] || ''),
  }
}

function handleCancelEditBgm() {
  editingBgm.value = null
}

function handleSaveBgm() {
  if (!editingBgm.value) return
  const newId = parseInt(editingBgm.value.value.trim())
  if (isNaN(newId)) {
    notify('请输入有效的 BGM ID', '', 'warning')
    return
  }
  const { seasonKey, index } = editingBgm.value
  const list = editingSeasonMappings.value[seasonKey]
  if (!list) return
  // 去重检查
  if (list.some((id, i) => id === newId && i !== index)) {
    notify('BGM ID 已存在', '该季中已有此 BGM ID', 'warning')
    return
  }
  list[index] = newId
  editingBgm.value = null
  // 如果该 BGM ID 的详情未加载过，懒加载
  if (!detailBangumiInfos.value.has(newId)) {
    getBatchBangumiDetailsApi([newId]).then(infos => {
      infos.forEach(info => {
        if (info.id) detailBangumiInfos.value.set(info.id, info)
      })
    }).catch(() => {})
  }
}

function handleDeleteBgm(seasonKey: string, index: number) {
  const list = editingSeasonMappings.value[seasonKey]
  if (!list) return
  list.splice(index, 1)
  // 如果该季度空了，删除整个季度
  if (list.length === 0) {
    delete editingSeasonMappings.value[seasonKey]
  }
}

// ── 删除整个季度 ──
function handleDeleteSeason(seasonKey: string) {
  delete editingSeasonMappings.value[seasonKey]
}

// ── 保存 / 删除 ──
async function handleSaveDetail() {
  if (!selectedItem.value) return
  const success = await store.updateMapping({
    tmdb_id: selectedItem.value.tmdb_id,
    tmdb_type: selectedItem.value.tmdb_type,
    season_mappings: editingSeasonMappings.value,
  })
  if (success) {
    notify('保存成功', '', 'success')
    router.push('/tmdb-bgm-mapping')
  } else {
    notify('保存失败', '', 'error')
  }
}

async function handleDeleteMapping() {
  if (!selectedItem.value) return
  const ok = await confirm({
    title: '删除映射',
    content: `确认删除 TMDB ID ${selectedItem.value.tmdb_id} (${selectedItem.value.tmdb_type}) 的映射？`,
    confirmColor: 'error',
  })
  if (!ok) return
  const success = await store.deleteMapping(selectedItem.value.tmdb_id, selectedItem.value.tmdb_type)
  if (success) {
    notify('已删除', '', 'success')
    router.push('/tmdb-bgm-mapping')
  }
}
</script>

<template>
  <v-container fluid class="pa-6">
    <!-- 页头 -->
    <div class="d-flex flex-wrap align-center mb-4 ga-3">
      <v-btn variant="text" icon="mdi-arrow-left" size="small" @click="router.push('/tmdb-bgm-mapping')" />
      <div class="flex-grow-1">
        <h1 class="text-h5 font-weight-bold d-inline">{{ getTmdbTitle() }}</h1>
        <span class="text-body-2 text-medium-emphasis ml-2">{{ getTmdbYear() }}</span>
        <p class="text-caption text-medium-emphasis mt-1">TMDB-BGM 映射详情</p>
      </div>
      <v-chip
        v-if="selectedItem"
        :color="selectedItem.tmdb_type === 'tv' ? 'success' : 'info'"
        size="small" variant="tonal" label
      >
        {{ selectedItem.tmdb_type === 'tv' ? '剧集' : '电影' }}
      </v-chip>
    </div>

    <!-- 未找到 -->
    <v-card v-if="!selectedItem" variant="outlined" rounded="xl" class="pa-8">
      <div class="text-center">
        <v-icon size="64" color="grey-lighten-1">mdi-link-off</v-icon>
        <p class="text-h6 mt-3 mb-2">未找到该映射</p>
        <p class="text-caption text-medium-emphasis mb-4">该映射可能已被删除</p>
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-arrow-left" @click="router.push('/tmdb-bgm-mapping')">
          返回列表
        </v-btn>
      </div>
    </v-card>

    <template v-else>
      <!-- TMDB 信息区 -->
      <v-card variant="outlined" rounded="xl" class="mb-4">
        <v-card-title class="text-subtitle-2 pa-4 pb-0">
          <v-icon start size="small" icon="mdi-information-outline" color="primary" />
          TMDB 信息
        </v-card-title>
        <v-card-text class="pa-4 pt-3">
          <template v-if="detailTmdbItem?.full_metadata">
            <div class="d-flex flex-wrap ga-3 text-body-2 mb-2">
              <span><strong>TMDB ID:</strong> {{ selectedItem.tmdb_id }}</span>
              <span v-if="detailTmdbItem.full_metadata.first_air_date || detailTmdbItem.full_metadata.release_date">
                <strong>年份:</strong> {{ (detailTmdbItem.full_metadata.first_air_date || detailTmdbItem.full_metadata.release_date)?.split('-')[0] }}
              </span>
            </div>
            <div v-if="detailTmdbItem.full_metadata.original_name || detailTmdbItem.full_metadata.original_title"
              class="text-caption text-medium-emphasis"
            >
              原名: {{ detailTmdbItem.full_metadata.original_name || detailTmdbItem.full_metadata.original_title }}
            </div>
          </template>
          <div v-else class="d-flex align-center ga-2">
            <v-progress-circular indeterminate size="20" color="primary" />
            <span class="text-caption text-medium-emphasis">加载 TMDB 数据...</span>
          </div>
        </v-card-text>
      </v-card>

      <!-- 季数映射区 -->
      <v-card variant="outlined" rounded="xl" class="mb-4">
        <v-card-title class="text-subtitle-2 pa-4 pb-0 d-flex align-center">
          <v-icon start size="small" icon="mdi-link-variant-plus" color="warning" />
          季数映射
          <v-spacer />
          <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="openAddSeasonDialog">
            添加季度
          </v-btn>
        </v-card-title>
        <v-card-text class="pa-4 pt-3">
          <v-progress-circular v-if="isLoadingBangumi" indeterminate size="20" color="primary" class="mb-2" />

          <div v-if="Object.keys(editingSeasonMappings).length === 0 && !isLoadingBangumi" class="text-center pa-4 text-medium-emphasis text-caption">
            暂无季数映射
          </div>

          <div v-else class="d-flex flex-column ga-2">
            <v-card
              v-for="seasonKey in Object.keys(editingSeasonMappings).sort((a, b) => parseInt(a) - parseInt(b))"
              :key="seasonKey"
              variant="outlined"
              rounded="xl"
              class="pa-3"
            >
              <!-- 季头部 -->
              <div class="d-flex align-center mb-2">
                <v-chip
                  :color="seasonKey === '0' ? 'info' : 'success'"
                  size="small" variant="tonal" label
                >
                  {{ seasonKey === '0' ? '电影' : `S${seasonKey}` }}
                </v-chip>
                <span class="text-caption text-medium-emphasis ml-2">
                  {{ editingSeasonMappings[seasonKey]?.length || 0 }} 个 BGM
                </span>
                <v-spacer />
                <v-btn size="x-small" variant="tonal" color="error" prepend-icon="mdi-delete-outline" @click="handleDeleteSeason(seasonKey)">删除季度</v-btn>
              </div>

              <!-- BGM ID 列表（每条一行） -->
              <div class="d-flex flex-column ga-1">
                <div
                  v-for="(bgmId, index) in editingSeasonMappings[seasonKey]"
                  :key="`${bgmId}-${index}`"
                  class="d-flex align-center ga-2 pa-2 rounded"
                >
                  <v-chip size="x-small" variant="tonal" label color="primary">{{ bgmId }}</v-chip>

                  <!-- 编辑模式 -->
                  <template v-if="editingBgm?.seasonKey === seasonKey && editingBgm?.index === index">
                    <v-text-field
                      v-model="editingBgm.value"
                      density="compact"
                      variant="outlined"
                      hide-details
                      class="mw-120px"
                      @keyup.enter="handleSaveBgm"
                    />
                    <v-btn size="x-small" variant="tonal" color="primary" icon="mdi-check" density="comfortable" @click="handleSaveBgm" />
                    <v-btn size="x-small" variant="tonal" color="grey" icon="mdi-close" density="comfortable" @click="handleCancelEditBgm" />
                  </template>

                  <!-- 展示模式 -->
                  <template v-else>
                    <div class="flex-grow-1">
                      <div class="text-caption font-weight-medium">{{ getBangumiName(bgmId) }}</div>
                      <div class="text-caption text-medium-emphasis">{{ getBangumiDate(bgmId) }} · {{ getBangumiEps(bgmId) }}</div>
                    </div>
                    <v-btn
                      size="x-small" variant="tonal" icon="mdi-open-in-new" color="info" density="comfortable"
                      :href="`https://bgm.tv/subject/${bgmId}`" target="_blank"
                    />
                    <v-btn size="x-small" variant="tonal" icon="mdi-pencil" color="info" density="comfortable" @click="handleEditBgm(seasonKey, index)" />
                    <v-btn size="x-small" variant="tonal" icon="mdi-delete" color="error" density="comfortable" @click="handleDeleteBgm(seasonKey, index)" />
                  </template>
                </div>
                <div v-if="!editingSeasonMappings[seasonKey]?.length" class="text-caption text-medium-emphasis pa-1">
                  无 BGM ID
                </div>
              </div>
            </v-card>
          </div>
        </v-card-text>
      </v-card>

      <!-- 操作栏 -->
      <div class="d-flex justify-end ga-3">
        <v-btn size="small" variant="tonal" color="error" prepend-icon="mdi-delete-outline" @click="handleDeleteMapping">
          删除映射
        </v-btn>
        <v-btn size="small" variant="tonal" color="grey" prepend-icon="mdi-close" @click="router.push('/tmdb-bgm-mapping')">返回列表</v-btn>
        <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-content-save" @click="handleSaveDetail">保存修改</v-btn>
      </div>
    </template>

    <!-- ═══════════════════════════════════════════ -->
    <!-- 添加季度弹框 -->
    <!-- ═══════════════════════════════════════════ -->
    <v-dialog v-model="showAddSeasonDialog" max-width="480" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-plus" class="mr-2" />
          添加映射
          <v-spacer />
          <v-btn size="small" variant="text" icon="mdi-close" @click="showAddSeasonDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-row density="compact">
            <v-col cols="4">
              <v-text-field v-model.number="addSeasonForm.season_number" label="季号" type="number" density="compact" variant="outlined" />
            </v-col>
            <v-col cols="8">
              <v-text-field v-model="addSeasonForm.bgm_ids" label="BGM ID (逗号分隔)" density="compact" variant="outlined"
                placeholder="12345, 67890" @keyup.enter="handleConfirmAddSeason" />
            </v-col>
          </v-row>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showAddSeasonDialog = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-check" @click="handleConfirmAddSeason">添加</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

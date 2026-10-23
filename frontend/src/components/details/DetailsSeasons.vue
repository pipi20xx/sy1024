<script setup lang="ts">
import { computed, ref } from 'vue'
import { useDetailsStore, useAiStore } from '@/stores'
import { testTranslationApi } from '@/api/ai'
import { useNotification, useConfirm } from '@/composables'
import JsonEditorDialog from '@/components/common/JsonEditorDialog.vue'

const store = useDetailsStore()
const aiStore = useAiStore()
const { notify } = useNotification()
const { confirm } = useConfirm()

const seasons = computed(() => store.itemDetails?.seasons || [])
const isEpisodeGroupView = computed(() => store.currentViewMode === 'episodegroup')

// 展开/收起状态管理：以 season_number 为 key 持久化展开状态，
// 避免保存图片后 loadDetails() 重新渲染导致展开状态丢失
const expandedSeasons = ref<Set<number>>(new Set())

function toggleSeasonExpanded(seasonNumber: number) {
  if (expandedSeasons.value.has(seasonNumber)) {
    expandedSeasons.value.delete(seasonNumber)
  } else {
    expandedSeasons.value.add(seasonNumber)
  }
  // 触发响应式更新
  expandedSeasons.value = new Set(expandedSeasons.value)
}

function isSeasonExpanded(seasonNumber: number): boolean {
  return expandedSeasons.value.has(seasonNumber)
}

// 编辑季/集
const showEditModal = ref(false)
const editType = ref<'season' | 'episode'>('season')
const editingData = ref<any>({})
const currentSeasonNum = ref(0)
const currentEpisodeNum = ref(0)
const isTranslating = ref<Record<string, boolean>>({})

// JSON 编辑
const showJsonEditor = ref(false)
const editingJsonData = ref<any>({})

// 演职员查看
const showCastModal = ref(false)
const castModalTitle = ref('')
const castList = ref<any[]>([])
const crewList = ref<any[]>([])

function getSeasonName(season: any): string {
  return season.metadata?.name || season.name || ''
}

function getSeasonOverview(season: any): string {
  return season.metadata?.overview || season.overview || ''
}

function getSeasonAirDate(season: any): string {
  const meta = season.metadata
  if (!meta) return ''
  const d = meta.air_date || meta.premiere_date || ''
  return d && d.length >= 10 ? d.substring(0, 10) : d
}

function getSeasonYear(season: any): string {
  const meta = season.metadata
  if (!meta) return ''
  if (meta.year) return String(meta.year)
  const dateStr = meta.air_date || meta.premiere_date || ''
  return dateStr ? dateStr.substring(0, 4) : ''
}

function getEpisodeDisplayName(ep: any): string {
  const name = ep.metadata?.name || ep.name
  const originalName = ep.metadata?.original_name || ep.original_name
  if (name && name !== '未命名' && name !== 'TBA') return name
  if (originalName && originalName !== name) return originalName
  const displayEp = isEpisodeGroupView.value ? (ep.custom_episode_number ?? ep.episode_number) : ep.episode_number
  return `第 ${displayEp} 集`
}

/** 剧集组视图下，显示原始TMDB编号 (S1E5) */
function getEpisodeOriginalRef(ep: any): string {
  if (!isEpisodeGroupView.value) return ''
  // 原始编号与剧集组编号相同时无需显示
  if (ep.season_number === ep.custom_season_number && ep.episode_number === ep.custom_episode_number) return ''
  return `S${ep.season_number}E${ep.episode_number}`
}

/** 获取显示用的集号（剧集组视图用custom，标准视图用原始） */
function getDisplayEpisodeNumber(ep: any): number {
  return isEpisodeGroupView.value ? (ep.custom_episode_number ?? ep.episode_number) : ep.episode_number
}

function getEpisodeAirDate(ep: any): string {
  const d = ep.metadata?.air_date || ep.air_date || ''
  return d && d.length >= 10 ? d.substring(0, 10) : d
}

function getImageUrl(path: string | undefined): string {
  if (!path) return ''
  if (!path.startsWith('/media-content') && !path.startsWith('http')) {
    const filename = path.split('/').pop()?.split('\\').pop()
    return `/media-content/${store.currentItemType}/${store.currentItemId}/images/${filename}`
  }
  return path
}

/** 占位图（横向用于集缩略图，竖向用于季海报） */
const EPISODE_PLACEHOLDER = '/static/placeholder-wide.png'
const SEASON_PLACEHOLDER = '/static/placeholder.png'

/** 获取集缩略图 URL，无图片时回退到占位图 */
function getEpisodeThumbUrl(path: string | undefined): string {
  return path ? getImageUrl(path) : EPISODE_PLACEHOLDER
}

/** 获取季海报 URL，无图片时回退到占位图 */
function getSeasonPosterUrl(path: string | undefined): string {
  return path ? getImageUrl(path) : SEASON_PLACEHOLDER
}

// 编辑季
function handleEditSeason(season: any) {
  editType.value = 'season'
  currentSeasonNum.value = season.season_number
  editingData.value = { ...season.metadata }
  showEditModal.value = true
}

// 编辑集
function handleEditEpisode(season: any, episode: any) {
  editType.value = 'episode'
  // 剧集组视图下使用TMDB原始编号（后端文件路径依赖此编号）
  currentSeasonNum.value = episode.season_number
  currentEpisodeNum.value = episode.episode_number
  editingData.value = { ...episode.metadata }
  showEditModal.value = true
}

// 保存编辑
async function handleAiTranslate(field: string, context: string) {
  const text = editingData.value[field]
  if (!text) { notify('提示', '没有可翻译的内容', 'warning'); return }
  if (!aiStore.config.enabled) { notify('提示', '请先在设置中开启 AI 服务', 'warning'); return }
  const key = `${editType.value}_${field}_${context}`
  isTranslating.value[key] = true
  try {
    const meta = store.itemDetails?.full_metadata
    const extra_info = {
      item_name: meta?.name || meta?.title || store.itemDetails?.name,
      item_id: store.currentItemId, item_type: store.currentItemType,
      item_genres: meta?.genres?.map((g: any) => g.name).join(', '),
      original_language: meta?.original_language,
      season_number: currentSeasonNum.value,
      ...(editType.value === 'episode' ? { episode_number: currentEpisodeNum.value } : {}),
    }
    const res = await testTranslationApi(text, context, extra_info)
    if (res.translated) { editingData.value[field] = res.translated; notify('翻译完成', '', 'success') }
  } catch (e: any) { notify('翻译失败', e.message || '未知错误', 'error') }
  finally { isTranslating.value[key] = false }
}

async function saveEdit() {
  let success = false
  if (editType.value === 'season') {
    success = await store.saveSeasonMetadata(currentSeasonNum.value, editingData.value)
  } else {
    success = await store.saveEpisodeMetadata(currentSeasonNum.value, currentEpisodeNum.value, editingData.value)
  }
  if (success) { notify('保存成功', '', 'success'); showEditModal.value = false }
  else notify('保存失败', '', 'error')
}

// JSON 编辑
function handleEditSeasonJson(season: any) {
  currentSeasonNum.value = season.season_number
  editingJsonData.value = season.metadata || {}
  showJsonEditor.value = true
}

function handleEditEpisodeJson(season: any, episode: any) {
  // 剧集组视图下使用TMDB原始编号
  currentSeasonNum.value = episode.season_number
  currentEpisodeNum.value = episode.episode_number
  editingJsonData.value = episode.metadata || {}
  showJsonEditor.value = true
}

async function saveJsonEdit(data: any) {
  let success = false
  if (editType.value === 'season') success = await store.saveSeasonMetadata(currentSeasonNum.value, data)
  else success = await store.saveEpisodeMetadata(currentSeasonNum.value, currentEpisodeNum.value, data)
  if (success) { notify('JSON 保存成功', '', 'success'); showJsonEditor.value = false }
  else notify('保存失败', '', 'error')
}

// 演职员查看
function handleShowCast(type: 'season' | 'episode', data: any) {
  castList.value = []
  crewList.value = []
  const credits = data.metadata?.credits || data.metadata?.casts
  if (credits) {
    if (credits.cast) castList.value = [...credits.cast]
    if (credits.crew) crewList.value = [...credits.crew]
    if (credits.guest_stars) castList.value = [...castList.value, ...credits.guest_stars]
  }
  if (type === 'season') {
    castModalTitle.value = `第 ${data.season_number} 季 - 演职员`
  } else {
    const displayNum = isEpisodeGroupView.value ? (data.custom_episode_number ?? data.episode_number) : data.episode_number
    const originalRef = getEpisodeOriginalRef(data)
    castModalTitle.value = `第 ${displayNum} 集${originalRef ? ` (${originalRef})` : ''} - 演职员`
  }
  showCastModal.value = true
}

// 删除季
async function handleDeleteSeason(seasonNumber: number, includeEpisodes: boolean) {
  const label = includeEpisodes ? '季和集' : '季'
  const ok = await confirm({
    title: '删除确认',
    content: `确定删除第 ${seasonNumber} ${label}的 Override 数据？此操作不可恢复。`,
    confirmColor: 'error',
  })
  if (!ok) return
  const success = await store.deleteSeason(seasonNumber, includeEpisodes)
  if (success) notify('已删除', '', 'success')
  else notify('删除失败', '', 'error')
}

// 删除集
async function handleDeleteEpisode(seasonNumber: number, episodeNumber: number) {
  const ok = await confirm({
    title: '删除确认',
    content: `确定删除 S${seasonNumber}E${episodeNumber} 的 Override 数据？`,
    confirmColor: 'error',
  })
  if (!ok) return
  const success = await store.deleteEpisode(seasonNumber, episodeNumber)
  if (success) notify('已删除', '', 'success')
  else notify('删除失败', '', 'error')
}

// ======== 季度网络图片下载 ========
const showSeasonWebDialog = ref(false)
const selectedSeasonWebImages = ref<number[]>([])

function isSeasonWebImageSelected(index: number) {
  return selectedSeasonWebImages.value.includes(index)
}

function toggleSeasonWebImage(index: number) {
  const idx = selectedSeasonWebImages.value.indexOf(index)
  if (idx >= 0) selectedSeasonWebImages.value.splice(idx, 1)
  else selectedSeasonWebImages.value.push(index)
}

const selectedSeasonWebImagesCount = computed(() => selectedSeasonWebImages.value.length)

function handleSelectAllSeasonWebImages() {
  if (selectedSeasonWebImages.value.length === store.seasonWebImages.length) {
    selectedSeasonWebImages.value = []
  } else {
    selectedSeasonWebImages.value = store.seasonWebImages.map((_: any, i: number) => i)
  }
}

async function handleOpenSeasonWebImages(season: any) {
  currentSeasonNum.value = season.season_number
  selectedSeasonWebImages.value = []
  showSeasonWebDialog.value = true
  await store.loadSeasonWebImages(season.season_number, ['poster'], ['tmdb'])
}

async function handleSaveSeasonWebImages() {
  const selected = store.seasonWebImages
    .filter((_: any, i: number) => selectedSeasonWebImages.value.includes(i))
    .map((img: any) => ({ url: img.full_url || img.preview_url, label: img.label || img.type || '' }))
  if (selected.length === 0) { notify('提示', '请选择图片', 'warning'); return }
  const success = await store.saveSelectedSeasonWebImages(currentSeasonNum.value, selected, 'overwrite')
  if (success) {
    notify('季度图片保存成功', '', 'success')
    selectedSeasonWebImages.value = []
    showSeasonWebDialog.value = false
  } else {
    notify('保存失败', '', 'error')
  }
}

// ======== 集网络图片下载 ========
const showEpisodeWebDialog = ref(false)
const selectedEpisodeWebImages = ref<number[]>([])

function isEpisodeWebImageSelected(index: number) {
  return selectedEpisodeWebImages.value.includes(index)
}

function toggleEpisodeWebImage(index: number) {
  const idx = selectedEpisodeWebImages.value.indexOf(index)
  if (idx >= 0) selectedEpisodeWebImages.value.splice(idx, 1)
  else selectedEpisodeWebImages.value.push(index)
}

const selectedEpisodeWebImagesCount = computed(() => selectedEpisodeWebImages.value.length)

function handleSelectAllEpisodeWebImages() {
  if (selectedEpisodeWebImages.value.length === store.episodeWebImages.length) {
    selectedEpisodeWebImages.value = []
  } else {
    selectedEpisodeWebImages.value = store.episodeWebImages.map((_: any, i: number) => i)
  }
}

async function handleOpenEpisodeWebImages(season: any, episode: any) {
  currentSeasonNum.value = episode.season_number
  currentEpisodeNum.value = episode.episode_number
  selectedEpisodeWebImages.value = []
  showEpisodeWebDialog.value = true
  await store.loadEpisodeWebImages(episode.season_number, episode.episode_number, ['thumb'], ['tmdb'])
}

async function handleSaveEpisodeWebImages() {
  const selected = store.episodeWebImages
    .filter((_: any, i: number) => selectedEpisodeWebImages.value.includes(i))
    .map((img: any) => ({ url: img.full_url || img.preview_url, label: img.label || img.type || '' }))
  if (selected.length === 0) { notify('提示', '请选择图片', 'warning'); return }
  const success = await store.saveSelectedEpisodeWebImages(currentSeasonNum.value, currentEpisodeNum.value, selected, 'overwrite')
  if (success) {
    notify('集图片保存成功', '', 'success')
    selectedEpisodeWebImages.value = []
    showEpisodeWebDialog.value = false
  } else {
    notify('保存失败', '', 'error')
  }
}
</script>

<template>
  <v-container fluid>
    <!-- 季度卡片列表 -->
    <div v-if="seasons.length" class="d-flex flex-column ga-3">
      <v-card v-for="season in seasons" :key="season.season_number" variant="outlined" rounded="lg" class="season-card">
        <!-- 上半部分：海报 + 季信息 -->
        <div class="d-flex flex-column flex-sm-row">
          <!-- 左侧竖版海报 -->
          <div class="season-poster-wrap flex-shrink-0">
            <v-img :src="getSeasonPosterUrl(season.poster_path)" :aspect-ratio="2/3" cover class="season-poster-img" min-width="120" width="100%" max-width="180">
              <template #error>
                <v-img :src="SEASON_PLACEHOLDER" :aspect-ratio="2/3" cover class="season-poster-img" min-width="120" width="100%" max-width="180" />
              </template>
            </v-img>
          </div>

          <!-- 右侧内容 -->
          <div class="flex-grow-1 pa-3 min-width-0 d-flex flex-column">
            <!-- 季度标题行 -->
            <div class="d-flex align-center ga-2 mb-1">
              <v-chip size="small" variant="flat" color="primary" label>第 {{ season.season_number }} 季</v-chip>
              <span v-if="getSeasonName(season)" class="text-medium-emphasis text-body-1">{{ getSeasonName(season) }}</span>
              <v-spacer />
              <!-- 操作按钮 -->
              <div class="d-flex ga-1 flex-shrink-0">
                <v-btn size="x-small" variant="tonal" icon="mdi-image-search" color="primary" density="comfortable" @click.stop="handleOpenSeasonWebImages(season)" />
                <v-btn size="x-small" variant="tonal" icon="mdi-account-group" color="info" density="comfortable" @click.stop="handleShowCast('season', season)" />
                <v-btn size="x-small" variant="tonal" icon="mdi-pencil" color="info" density="comfortable" :disabled="season.source !== 'override'" @click.stop="handleEditSeason(season)" />
                <v-btn size="x-small" variant="tonal" icon="mdi-code-block-braces" color="info" density="comfortable" :disabled="season.source !== 'override'" @click.stop="handleEditSeasonJson(season)" />
                <v-btn v-if="season.source === 'override'" size="x-small" variant="tonal" icon="mdi-delete" color="error" density="comfortable" @click.stop="handleDeleteSeason(season.season_number, false)" />
                <v-btn v-if="season.source === 'override'" size="x-small" variant="tonal" icon="mdi-delete-sweep" color="error" density="comfortable" @click.stop="handleDeleteSeason(season.season_number, true)" />
              </div>
            </div>
            <!-- 播出日期 + 来源 + 集数 -->
            <div class="d-flex align-center ga-1 mb-1">
              <span v-if="getSeasonAirDate(season)" class="text-caption text-medium-emphasis">{{ getSeasonAirDate(season) }}</span>
              <span v-else-if="getSeasonYear(season)" class="text-caption text-medium-emphasis">{{ getSeasonYear(season) }}</span>
              <v-chip v-if="season.source === 'override'" size="x-small" variant="tonal" color="warning">Override</v-chip>
              <v-chip v-if="season.source === 'primary'" size="x-small" variant="tonal" color="success">Primary</v-chip>
              <span class="text-caption text-medium-emphasis">{{ season.episodes?.length || 0 }} 集</span>
            </div>
            <!-- 季简介 -->
            <div v-if="getSeasonOverview(season)" class="text-body-2 text-medium-emphasis line-clamp-3 mb-2">{{ getSeasonOverview(season) }}</div>

            <!-- 剧集列表按钮（仅折叠时显示） -->
            <v-alert v-if="!season.episodes?.length" type="info" variant="tonal" density="compact" class="mt-auto">暂无集数据</v-alert>
          </div>
        </div>

        <!-- 下半部分：剧集列表（全宽，左边缘与海报对齐） -->
        <div v-if="season.episodes?.length">
          <div class="d-flex align-center pa-2 cursor-pointer season-expand-header" @click="toggleSeasonExpanded(season.season_number)">
            <v-icon start size="small" :icon="isSeasonExpanded(season.season_number) ? 'mdi-chevron-down' : 'mdi-chevron-right'" />
            <span class="text-body-2 font-weight-medium">剧集列表 ({{ season.episodes.length }})</span>
          </div>
          <v-expand-transition>
            <div v-show="isSeasonExpanded(season.season_number)">
              <div class="d-flex flex-column ga-2 pa-2">
                <v-card v-for="ep in season.episodes" :key="ep.episode_number" variant="outlined" rounded="lg" class="episode-card">
                  <div class="d-flex flex-column flex-sm-row">
                    <!-- 左侧缩略图 -->
                    <div class="episode-thumb-wrap flex-shrink-0">
                      <v-img :src="getEpisodeThumbUrl(ep.thumb_path)" :aspect-ratio="16/9" cover min-width="160" width="100%" max-width="240">
                        <template #error>
                          <v-img :src="EPISODE_PLACEHOLDER" :aspect-ratio="16/9" cover min-width="160" width="100%" max-width="240" />
                        </template>
                      </v-img>
                    </div>

                    <!-- 右侧内容 -->
                    <div class="flex-grow-1 pa-3 min-width-0 d-flex flex-column justify-center">
                      <!-- 标题行 -->
                      <div class="d-flex align-center ga-1 mb-1">
                        <v-chip size="x-small" variant="flat" color="primary" label>{{ getDisplayEpisodeNumber(ep) }}</v-chip>
                        <span class="font-weight-medium text-body-2 text-truncate">{{ getEpisodeDisplayName(ep) }}</span>
                        <v-spacer />
                        <!-- 操作按钮 -->
                        <div class="d-flex ga-1 flex-shrink-0">
                          <v-btn size="x-small" variant="tonal" icon="mdi-image-search" color="primary" density="comfortable" @click.stop="handleOpenEpisodeWebImages(season, ep)" />
                          <v-btn size="x-small" variant="tonal" icon="mdi-account-group" color="info" density="comfortable" @click.stop="handleShowCast('episode', ep)" />
                          <v-btn size="x-small" variant="tonal" icon="mdi-pencil" color="info" density="comfortable" :disabled="ep.source !== 'override'" @click.stop="handleEditEpisode(season, ep)" />
                          <v-btn size="x-small" variant="tonal" icon="mdi-code-block-braces" color="info" density="comfortable" :disabled="ep.source !== 'override'" @click.stop="handleEditEpisodeJson(season, ep)" />
                          <v-btn v-if="ep.source === 'override'" size="x-small" variant="tonal" icon="mdi-delete" color="error" density="comfortable" @click.stop="handleDeleteEpisode(ep.season_number!, ep.episode_number!)" />
                        </div>
                      </div>
                      <!-- 播出日期 + 来源标签 -->
                      <div class="d-flex align-center ga-1 mb-1">
                        <span v-if="getEpisodeAirDate(ep)" class="text-caption text-medium-emphasis">{{ getEpisodeAirDate(ep) }}</span>
                        <v-chip v-if="ep.source === 'override'" size="x-small" variant="tonal" color="warning">Override</v-chip>
                        <v-chip v-else-if="ep.source === 'primary'" size="x-small" variant="tonal" color="success">Primary</v-chip>
                        <span v-if="getEpisodeOriginalRef(ep)" class="text-caption text-medium-emphasis">标准: {{ getEpisodeOriginalRef(ep) }}</span>
                      </div>
                      <!-- 简介 -->
                      <div v-if="ep.metadata?.overview" class="text-body-2 text-medium-emphasis line-clamp-3">{{ ep.metadata.overview }}</div>
                    </div>
                  </div>
                </v-card>
              </div>
            </div>
          </v-expand-transition>
        </div>
      </v-card>
    </div>

    <v-alert v-else type="info" variant="tonal" class="text-center">
      <v-icon size="48" class="mb-2">mdi-television-off</v-icon>
      <div>暂无季度数据</div>
    </v-alert>

    <!-- 编辑季/集弹框 -->
    <v-dialog v-model="showEditModal" max-width="600" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon :icon="editType === 'season' ? 'mdi-folder-edit' : 'mdi-movie-edit'" class="mr-2" />
          {{ editType === 'season' ? '编辑季元数据' : '编辑集元数据' }}
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showEditModal = false" />
        </v-card-title>
        <v-divider />
        <v-card-text>
          <v-form @submit.prevent="saveEdit">
            <v-text-field v-model="editingData.name" :label="editType === 'season' ? '季度标题/名称' : '分集标题/名称'" density="compact" variant="outlined" class="mb-2">
              <template #append-inner>
                <v-btn :loading="isTranslating[`${editType}_name_${editType === 'season' ? 'season_title' : 'episode_title'}`]" icon size="x-small" variant="text" @click="handleAiTranslate('name', editType === 'season' ? 'season_title' : 'episode_title')">
                  <v-icon size="small">mdi-translate</v-icon>
                </v-btn>
              </template>
            </v-text-field>
            <v-textarea v-model="editingData.overview" :label="editType === 'season' ? '季度简介' : '分集简介'" density="compact" variant="outlined" rows="4" auto-grow class="mb-2">
              <template #append-inner>
                <v-btn :loading="isTranslating[`${editType}_overview_${editType === 'season' ? 'season_overview' : 'episode_overview'}`]" icon size="x-small" variant="text" @click="handleAiTranslate('overview', editType === 'season' ? 'season_overview' : 'episode_overview')">
                  <v-icon size="small">mdi-translate</v-icon>
                </v-btn>
              </template>
            </v-textarea>
            <v-text-field v-model="editingData.air_date" label="首播日期" density="compact" variant="outlined" placeholder="YYYY-MM-DD" />
          </v-form>
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showEditModal = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-content-save" @click="saveEdit" :loading="store.isLoading">保存</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- JSON 编辑弹框 -->
    <JsonEditorDialog
      v-model="showJsonEditor"
      :initial-data="editingJsonData"
      :loading="store.isLoading"
      @confirm="saveJsonEdit"
    />

    <!-- 演职员查看弹框 -->
    <v-dialog v-model="showCastModal" max-width="800" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-account-group" class="mr-2" />
          {{ castModalTitle }}
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showCastModal = false" />
        </v-card-title>
        <v-divider />
        <v-card-text>
          <div v-if="castList.length > 0" class="mb-4">
            <div class="text-subtitle-2 font-weight-bold mb-2">演员 / 客串</div>
            <v-row>
              <v-col v-for="person in castList.slice(0, 50)" :key="person.id" cols="6" sm="4" md="3">
                <v-list-item density="compact">
                  <template #prepend>
                    <v-avatar size="48" rounded class="mr-3">
                      <v-img v-if="person.profile_path" :src="`/tmdb-mock/t/p/w92${person.profile_path}`">
                        <template #error><v-icon>mdi-account</v-icon></template>
                      </v-img>
                      <v-icon v-else>mdi-account</v-icon>
                    </v-avatar>
                  </template>
                  <v-list-item-title class="text-body-2 text-truncate">{{ person.name }}</v-list-item-title>
                  <v-list-item-subtitle class="text-caption text-truncate">{{ person.character }}</v-list-item-subtitle>
                </v-list-item>
              </v-col>
            </v-row>
            <v-divider class="my-3" />
          </div>

          <div v-if="crewList.length > 0">
            <div class="text-subtitle-2 font-weight-bold mb-2">制作人员</div>
            <div class="d-flex flex-wrap ga-2">
              <v-chip v-for="person in crewList.slice(0, 20)" :key="`${person.id}-${person.job}`" size="small" variant="tonal" label>
                {{ person.name }} ({{ person.job }})
              </v-chip>
            </div>
          </div>

          <v-alert v-if="castList.length === 0 && crewList.length === 0" type="info" variant="tonal" class="text-center mt-4">
            <v-icon size="48" class="mb-2">mdi-account-off-outline</v-icon>
            <div>暂无演职员信息</div>
          </v-alert>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- 季度网络图片下载弹框 -->
    <v-dialog v-model="showSeasonWebDialog" max-width="800" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-image-search" class="mr-2" />
          从 TMDb 下载季度海报 (第 {{ currentSeasonNum }} 季)
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showSeasonWebDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text>
          <div v-if="store.isSeasonImagesLoading" class="text-center pa-8">
            <v-progress-circular indeterminate color="primary" />
            <p class="mt-2 text-medium-emphasis">正在从 TMDb 搜索海报...</p>
          </div>
          <template v-else-if="store.seasonWebImages.length">
            <div class="d-flex align-center mb-3">
              <span class="text-subtitle-2 font-weight-bold">搜索结果 ({{ store.seasonWebImages.length }})</span>
              <v-spacer />
              <v-btn size="x-small" variant="tonal" @click="handleSelectAllSeasonWebImages">
                {{ selectedSeasonWebImagesCount === store.seasonWebImages.length ? '取消全选' : '全选' }}
              </v-btn>
            </div>
            <v-row>
              <v-col v-for="(img, index) in store.seasonWebImages" :key="index" cols="6" sm="4" md="3">
                <v-card variant="outlined" :color="isSeasonWebImageSelected(index) ? 'primary' : undefined" class="cursor-pointer image-card" @click="toggleSeasonWebImage(index)">
                  <div class="image-card__poster">
                    <v-img :src="img.preview_url || img.full_url" :aspect-ratio="2/3" cover class="image-card__img">
                      <template #error><v-sheet class="d-flex align-center justify-center fill-height"><v-icon>mdi-image-off</v-icon></v-sheet></template>
                    </v-img>
                  </div>
                  <v-card-text class="pa-2 text-center text-caption text-truncate">{{ img.source }} · {{ img.lang }}</v-card-text>
                  <v-overlay :model-value="isSeasonWebImageSelected(index)" contained persistent class="align-center justify-center">
                    <v-icon size="40" color="primary">mdi-check-circle</v-icon>
                  </v-overlay>
                </v-card>
              </v-col>
            </v-row>
          </template>
          <v-alert v-else type="info" variant="tonal" class="text-center">
            <v-icon size="48" class="mb-2">mdi-image-off-outline</v-icon>
            <div>未找到符合条件的季度海报</div>
          </v-alert>
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <span class="text-caption text-medium-emphasis">已选 {{ selectedSeasonWebImagesCount }} 张</span>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showSeasonWebDialog = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-content-save" :disabled="selectedSeasonWebImagesCount === 0" @click="handleSaveSeasonWebImages">保存选中 ({{ selectedSeasonWebImagesCount }})</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 集网络图片下载弹框 -->
    <v-dialog v-model="showEpisodeWebDialog" max-width="800" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-image-search" class="mr-2" />
          从 TMDb 下载集图片 (S{{ currentSeasonNum }}E{{ currentEpisodeNum }})
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showEpisodeWebDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text>
          <div v-if="store.isEpisodeImagesLoading" class="text-center pa-8">
            <v-progress-circular indeterminate color="primary" />
            <p class="mt-2 text-medium-emphasis">正在从 TMDb 搜索集图片...</p>
          </div>
          <template v-else-if="store.episodeWebImages.length">
            <div class="d-flex align-center mb-3">
              <span class="text-subtitle-2 font-weight-bold">搜索结果 ({{ store.episodeWebImages.length }})</span>
              <v-spacer />
              <v-btn size="x-small" variant="tonal" @click="handleSelectAllEpisodeWebImages">
                {{ selectedEpisodeWebImagesCount === store.episodeWebImages.length ? '取消全选' : '全选' }}
              </v-btn>
            </div>
            <v-row>
              <v-col v-for="(img, index) in store.episodeWebImages" :key="index" cols="12" sm="6" md="4">
                <v-card variant="outlined" :color="isEpisodeWebImageSelected(index) ? 'primary' : undefined" class="cursor-pointer image-card" @click="toggleEpisodeWebImage(index)">
                  <div class="image-card__poster">
                    <v-img :src="img.preview_url || img.full_url" :aspect-ratio="16/9" cover class="image-card__img">
                      <template #error><v-sheet class="d-flex align-center justify-center fill-height"><v-icon>mdi-image-off</v-icon></v-sheet></template>
                    </v-img>
                  </div>
                  <v-card-text class="pa-2 text-center text-caption text-truncate">{{ img.source }} · {{ img.lang }}</v-card-text>
                  <v-overlay :model-value="isEpisodeWebImageSelected(index)" contained persistent class="align-center justify-center">
                    <v-icon size="40" color="primary">mdi-check-circle</v-icon>
                  </v-overlay>
                </v-card>
              </v-col>
            </v-row>
          </template>
          <v-alert v-else type="info" variant="tonal" class="text-center">
            <v-icon size="48" class="mb-2">mdi-image-off-outline</v-icon>
            <div>未找到符合条件的集图片</div>
          </v-alert>
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <span class="text-caption text-medium-emphasis">已选 {{ selectedEpisodeWebImagesCount }} 张</span>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showEpisodeWebDialog = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-content-save" :disabled="selectedEpisodeWebImagesCount === 0" @click="handleSaveEpisodeWebImages">保存选中 ({{ selectedEpisodeWebImagesCount }})</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

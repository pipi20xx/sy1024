<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDetailsStore } from '@/stores'
import { useNotification, useConfirm } from '@/composables'
import { api } from '@/api/client'
import { getBangumiRecommendation, updateMetadataFromBangumi, updateTmdbMetadata, getTmdbUpdateConfig, setTmdbUpdateConfig, updateMetadataFromEmby } from '@/api/details'
import SpecialEpisodeModal from './SpecialEpisodeModal.vue'
import EpisodeGroupModal from './EpisodeGroupModal.vue'
import JsonEditorDialog from '@/components/common/JsonEditorDialog.vue'

const store = useDetailsStore()
const { notify } = useNotification()
const { confirm } = useConfirm()

const isMovie = computed(() => store.currentItemType === 'tmdb-movies2')

const showModeDialog = ref(false)
const selectedMode = ref<'merge' | 'overwrite'>('merge')
const pendingAction = ref<string>('')

const showJsonEditor = ref(false)
const editingJsonData = ref<any>({})

// TMDB 更新弹框
const showTmdbUpdate = ref(false)
const tmdbLoading = ref(false)
const tmdbFields = ref<string[]>([])
const tmdbOverwrite = ref(true)
const tmdbLang = ref('zh-CN')
const tmdbTriggerEmbyRefresh = ref(false)
const tmdbConfig = ref<any>({})

// 更新目标选择 (仅 TV)
const tmdbUpdateTarget = ref<'series_only' | 'whole_series' | 'season' | 'episode'>('series_only')
const tmdbTargetSeason = ref<number | null>(null)
const tmdbTargetEpisode = ref<number | null>(null)
const tmdbUpdateSeasonEpisodes = ref(false)

const langOptions = [
  { title: '简体中文 (zh-CN)', value: 'zh-CN' },
  { title: '繁体中文 (zh-TW)', value: 'zh-TW' },
  { title: '香港中文 (zh-HK)', value: 'zh-HK' },
  { title: '新加坡中文 (zh-SG)', value: 'zh-SG' },
  { title: '英语 (en-US)', value: 'en-US' },
  { title: '日语 (ja-JP)', value: 'ja-JP' },
  { title: '韩语 (ko-KR)', value: 'ko-KR' },
]

// 字段定义
const MOVIE_FIELDS = [
  { title: '标题 (title)', value: 'title' },
  { title: '原名 (original_title)', value: 'original_title' },
  { title: '简介 (overview)', value: 'overview' },
  { title: '评分 (vote_average)', value: 'vote_average' },
  { title: '上映日期 (release_date)', value: 'release_date' },
  { title: '时长 (runtime)', value: 'runtime' },
  { title: '标语 (tagline)', value: 'tagline' },
  { title: '类型 (genres)', value: 'genres' },
  { title: '演职员 (casts)', value: 'casts' },
  { title: '分级信息 (releases)', value: 'releases' },
  { title: '预告片 (trailers)', value: 'trailers' },
  { title: '制作公司 (production_companies)', value: 'production_companies' },
  { title: '制作国家 (production_countries)', value: 'production_countries' },
  { title: '语言 (spoken_languages)', value: 'spoken_languages' },
  { title: '关键词 (keywords)', value: 'keywords' },
]

const TV_FIELDS = [
  { title: '名称 (name)', value: 'name' },
  { title: '原名 (original_name)', value: 'original_name' },
  { title: '简介 (overview)', value: 'overview' },
  { title: '标语 (tagline)', value: 'tagline' },
  { title: '评分 (vote_average)', value: 'vote_average' },
  { title: '首播日期 (first_air_date)', value: 'first_air_date' },
  { title: '最新日期 (last_air_date)', value: 'last_air_date' },
  { title: '状态 (status)', value: 'status' },
  { title: '类型 (genres)', value: 'genres' },
  { title: '演职员 (credits)', value: 'credits' },
  { title: '预告片 (trailers)', value: 'trailers' },
  { title: '电视网 (networks)', value: 'networks' },
  { title: '制作公司 (production_companies)', value: 'production_companies' },
  { title: '关键词 (keywords)', value: 'keywords' },
  { title: '语言列表 (languages)', value: 'languages' },
]

const SEASON_FIELDS = [
  { title: '季名称 (name)', value: 'name' },
  { title: '季简介 (overview)', value: 'overview' },
  { title: '评分 (vote_average)', value: 'vote_average' },
  { title: '首播日期 (air_date)', value: 'air_date' },
  { title: '演职员 (credits)', value: 'credits' },
  { title: '预告片 (trailers)', value: 'trailers' },
]

const EPISODE_FIELDS = [
  { title: '集名称 (name)', value: 'name' },
  { title: '集简介 (overview)', value: 'overview' },
  { title: '评分 (vote_average)', value: 'vote_average' },
  { title: '播出日期 (air_date)', value: 'air_date' },
  { title: '时长 (runtime)', value: 'runtime' },
  { title: '演职员 (credits)', value: 'credits' },
  { title: '预告片 (trailers)', value: 'trailers' },
]

const DEFAULT_PRESETS: Record<string, string[]> = {
  movie: ['title', 'overview', 'original_title', 'vote_average', 'runtime', 'genres', 'tagline', 'spoken_languages'],
  tv: ['name', 'overview', 'original_name', 'vote_average', 'first_air_date', 'genres', 'last_air_date', 'tagline'],
  season: ['name', 'overview', 'air_date', 'vote_average'],
  episode: ['name', 'overview', 'vote_average', 'air_date', 'runtime'],
}

const tmdbEffectiveItemType = computed(() => {
  if (isMovie.value) return 'movie'
  if (tmdbUpdateTarget.value === 'season') return 'season'
  if (tmdbUpdateTarget.value === 'episode') return 'episode'
  return 'tv'
})

const tmdbAvailableFields = computed(() => {
  if (tmdbEffectiveItemType.value === 'movie') return MOVIE_FIELDS
  if (tmdbEffectiveItemType.value === 'tv') return TV_FIELDS
  if (tmdbEffectiveItemType.value === 'season') return SEASON_FIELDS
  if (tmdbEffectiveItemType.value === 'episode') return EPISODE_FIELDS
  return []
})

function selectAllTmdbFields() {
  tmdbFields.value = tmdbAvailableFields.value.map(f => f.value)
}

function deselectAllTmdbFields() {
  tmdbFields.value = []
}

function loadTmdbSavedSelection() {
  const key = `tmdb_update_fields_${tmdbEffectiveItemType.value}`
  const saved = tmdbConfig.value?.[key]
  if (saved && Array.isArray(saved)) {
    const validKeys = new Set(tmdbAvailableFields.value.map(f => f.value))
    tmdbFields.value = saved.filter((k: string) => validKeys.has(k))
  } else {
    const preset = DEFAULT_PRESETS[tmdbEffectiveItemType.value]
    if (preset) tmdbFields.value = [...preset]
    else selectAllTmdbFields()
  }
  if (tmdbConfig.value?.tmdb_update_language) tmdbLang.value = tmdbConfig.value.tmdb_update_language
  if (tmdbConfig.value?.tmdb_update_overwrite !== undefined) tmdbOverwrite.value = tmdbConfig.value.tmdb_update_overwrite
  if (tmdbConfig.value?.tmdb_update_trigger_refresh !== undefined) tmdbTriggerEmbyRefresh.value = tmdbConfig.value.tmdb_update_trigger_refresh
}

async function saveTmdbSelection() {
  const key = `tmdb_update_fields_${tmdbEffectiveItemType.value}`
  if (!tmdbConfig.value) tmdbConfig.value = {}
  tmdbConfig.value[key] = tmdbFields.value
  tmdbConfig.value.tmdb_update_language = tmdbLang.value
  tmdbConfig.value.tmdb_update_overwrite = tmdbOverwrite.value
  tmdbConfig.value.tmdb_update_trigger_refresh = tmdbTriggerEmbyRefresh.value
  try {
    await setTmdbUpdateConfig(tmdbConfig.value)
  } catch (e) {
    console.error('Failed to save config', e)
  }
}

watch(showTmdbUpdate, async (v) => {
  if (v) {
    tmdbUpdateTarget.value = 'series_only'
    tmdbTargetSeason.value = 1
    tmdbTargetEpisode.value = 1
    tmdbUpdateSeasonEpisodes.value = false
    try {
      tmdbConfig.value = await getTmdbUpdateConfig()
    } catch (e) {
      console.error('Failed to load config', e)
      tmdbConfig.value = {}
    }
    loadTmdbSavedSelection()
  }
})

watch(tmdbEffectiveItemType, () => {
  loadTmdbSavedSelection()
})

async function handleTmdbUpdate() {
  if (tmdbFields.value.length === 0) {
    notify('请至少选择一个要更新的字段', '', 'warning')
    return
  }
  if (tmdbEffectiveItemType.value === 'season' && tmdbTargetSeason.value === null) {
    notify('请输入季号', '', 'warning')
    return
  }
  if (tmdbEffectiveItemType.value === 'episode' && (tmdbTargetSeason.value === null || tmdbTargetEpisode.value === null)) {
    notify('请输入季号和集号', '', 'warning')
    return
  }

  saveTmdbSelection()

  let shouldUpdateChildren = false
  if (tmdbEffectiveItemType.value === 'season' && tmdbUpdateSeasonEpisodes.value) shouldUpdateChildren = true
  if (tmdbUpdateTarget.value === 'whole_series') shouldUpdateChildren = true

  tmdbLoading.value = true
  try {
    await updateTmdbMetadata(
      tmdbEffectiveItemType.value as 'movie' | 'tv' | 'season' | 'episode',
      store.currentItemId,
      {
        fields_to_update: tmdbFields.value,
        overwrite: tmdbOverwrite.value,
        trigger_emby_refresh: tmdbTriggerEmbyRefresh.value,
        update_season_episodes: shouldUpdateChildren,
      },
      tmdbLang.value,
      tmdbTargetSeason.value || undefined,
      tmdbTargetEpisode.value || undefined
    )
    notify('TMDB 元数据更新成功', '', 'success')
    showTmdbUpdate.value = false
    await store.loadDetails()
  } catch (e: any) {
    notify('TMDB 更新失败: ' + (e.response?.data?.detail || e.message), '', 'error')
  } finally {
    tmdbLoading.value = false
  }
}

// Bangumi 更新弹框
const showBangumiUpdate = ref(false)
const bangumiLoading = ref(false)
const bangumiRecommendLoading = ref(false)
const bangumiId = ref<number | null>(null)
const bangumiTitle = ref('')
const bangumiStatus = ref<'none' | 'linked' | 'recommended'>('none')
const bangumiScore = ref<number | null>(null)
const bangumiType = ref<number | null>(null)
const bangumiPlatform = ref('')
const bangumiYear = ref('')
const bangumiSource = ref('')
const bangumiForceRefresh = ref(false)
const bangumiUseWhitelist = ref(false)
const bangumiFields = ref<string[]>(['title', 'overview', 'tags', 'vote_average'])
const bangumiMode = ref<'merge' | 'overwrite'>('merge')

const bangumiFieldOptions = [
  { title: '标题 (title/name)', value: 'title' },
  { title: '原名 (original_title/original_name)', value: 'original_title' },
  { title: '简介 (overview)', value: 'overview' },
  { title: '标签 (tags)', value: 'tags' },
  { title: '评分 (vote_average)', value: 'vote_average' },
  { title: '日期 (release_date/first_air_date)', value: 'release_date' },
]

function getBgmTypeName(type: number | null) {
  if (!type) return '未知类型'
  const map: Record<number, string> = { 1: '书籍', 2: '动画', 3: '音乐', 4: '游戏', 6: '三次元' }
  return map[type] || '其他'
}

async function fetchBangumiRecommendation() {
  bangumiRecommendLoading.value = true
  bangumiId.value = null
  bangumiTitle.value = ''
  bangumiStatus.value = 'none'
  bangumiScore.value = null
  bangumiType.value = null
  bangumiPlatform.value = ''
  bangumiYear.value = ''
  bangumiSource.value = ''

  try {
    const res = await getBangumiRecommendation(store.currentItemType as any, store.currentItemId)
    bangumiStatus.value = res.status
    if (res.bangumi_id) {
      bangumiId.value = res.bangumi_id
      bangumiTitle.value = res.bangumi_title || ''
      bangumiScore.value = res.score ?? null
      bangumiType.value = res.type ?? null
      bangumiPlatform.value = res.platform_cn || ''
      bangumiYear.value = res.year || ''
      bangumiSource.value = res.source || ''
    }
  } catch (e: any) {
    console.error('获取 Bangumi 推荐失败', e)
  } finally {
    bangumiRecommendLoading.value = false
  }
}

function selectAllBangumiFields() {
  bangumiFields.value = ['title', 'original_title', 'overview', 'tags', 'vote_average', 'release_date']
}

function deselectAllBangumiFields() {
  bangumiFields.value = []
}

async function handleBangumiUpdate() {
  if (!bangumiId.value) {
    notify('请输入 Bangumi ID', '', 'warning')
    return
  }
  if (bangumiFields.value.length === 0) {
    notify('请至少选择一个字段', '', 'warning')
    return
  }

  bangumiLoading.value = true
  try {
    const res = await updateMetadataFromBangumi(
      store.currentItemType as any,
      store.currentItemId,
      bangumiId.value,
      bangumiFields.value,
      bangumiForceRefresh.value,
      bangumiUseWhitelist.value,
      bangumiMode.value
    )
    if (res.success) {
      notify(res.message || 'Bangumi 更新成功', '', 'success')
      showBangumiUpdate.value = false
      await store.loadDetails()
    } else {
      notify(res.message || '更新失败', '', 'error')
    }
  } catch (e: any) {
    notify('Bangumi 更新失败: ' + (e.response?.data?.detail || e.message), '', 'error')
  } finally {
    bangumiLoading.value = false
  }
}

watch(showBangumiUpdate, (v) => { if (v) fetchBangumiRecommendation() })

// Emby 更新弹框
const showEmbyUpdate = ref(false)
const embyLoading = ref(false)
const embyFields = ref<string[]>(['title', 'overview', 'genres', 'tags'])
const embyUpdateChildren = ref(false)
const embyChildFields = ref<string[]>(['season_name', 'season_overview', 'episode_name', 'episode_overview'])

const embyFieldOptions = [
  { title: '标题 (Title/Name)', value: 'title' },
  { title: '原始标题', value: 'original_title' },
  { title: '简介 (Overview)', value: 'overview' },
  { title: '类型 (Genres)', value: 'genres' },
  { title: '标签 (Tags)', value: 'tags' },
  { title: '标语 (Tagline)', value: 'tagline' },
  { title: '首播/上映日期', value: 'air_date' },
  { title: '完结日期', value: 'end_date' },
  { title: '评分 (Vote Average)', value: 'vote_average' },
]

const embyChildFieldOptions = [
  { title: '季名称', value: 'season_name' },
  { title: '季简介', value: 'season_overview' },
  { title: '季播出年份', value: 'season_air_date' },
  { title: '集标题', value: 'episode_name' },
  { title: '集简介', value: 'episode_overview' },
  { title: '集播出日期', value: 'episode_air_date' },
]

async function handleEmbyUpdate() {
  let fields = [...embyFields.value]
  const recursive = !isMovie.value && embyUpdateChildren.value
  if (recursive) {
    fields.push(...embyChildFields.value)
  }
  embyLoading.value = true
  try {
    const res = await updateMetadataFromEmby(
      store.currentItemType as any,
      store.currentItemId,
      fields,
      recursive
    )
    notify(res.message || 'Emby 更新成功', '', 'success')
    showEmbyUpdate.value = false
    await store.loadDetails()
  } catch (e: any) {
    notify('Emby 更新失败: ' + (e.response?.data?.detail || e.message), '', 'error')
  } finally {
    embyLoading.value = false
  }
}

// 备份管理弹框
const showBackupManager = ref(false)
const backupLoading = ref(false)
const backups = ref<any[]>([])

async function loadBackups() {
  backupLoading.value = true
  try {
    backups.value = await api.get(`/api/items/${store.currentItemType}/${store.currentItemId}/backups`)
  } catch (e: any) {
    console.error('Failed to load backups', e)
    backups.value = []
  } finally {
    backupLoading.value = false
  }
}

async function handleRestoreBackup(backupName: string) {
  const ok = await confirm({ title: '恢复备份', content: `确认恢复备份？当前数据将被覆盖。`, confirmColor: 'warning' })
  if (!ok) return
  try {
    await api.post(`/api/items/${store.currentItemType}/${store.currentItemId}/backups/${encodeURIComponent(backupName)}/restore`, {})
    notify('已恢复备份', '', 'success')
    await loadBackups()
    await store.loadDetails()
  } catch (e: any) {
    notify('恢复失败', e.message, 'error')
  }
}

async function handleDeleteBackup(backupName: string) {
  const ok = await confirm({ title: '删除备份', content: `确定要删除该备份吗？此操作不可恢复。`, confirmColor: 'error' })
  if (!ok) return
  try {
    await api.delete(`/api/items/${store.currentItemType}/${store.currentItemId}/backups/${encodeURIComponent(backupName)}`)
    notify('已删除备份', '', 'success')
    await loadBackups()
  } catch (e: any) {
    notify('删除失败', e.message, 'error')
  }
}

async function handleCreateBackup() {
  try {
    await api.post(`/api/items/${store.currentItemType}/${store.currentItemId}/backups`, {})
    notify('备份已创建', '', 'success')
    await loadBackups()
  } catch (e: any) {
    notify('创建失败', e.message, 'error')
  }
}

watch(showBackupManager, (v) => { if (v) loadBackups() })

// 外部ID弹框
const showExternalIds = ref(false)
const externalIdsLoading = ref(false)
const mainExternalIds = ref<Record<string, any>>({})
const seasons = ref<any[]>([])
const newSeasonForm = ref({ season_number: 1, imdb_id: '', tvdb_id: null as number | null, douban_id: null as number | null, bgm_id: '' })
const showExternalIdsJson = ref(false)

async function loadExternalIds() {
  if (!store.currentItemId) return
  externalIdsLoading.value = true
  try {
    const data: any = await api.get(`/api/items/${store.currentItemType}/${store.currentItemId}/externalids`)
    mainExternalIds.value = data.external_ids || {}
    seasons.value = data.seasons || []
  } catch (e) {
    mainExternalIds.value = {}
    seasons.value = []
  } finally {
    externalIdsLoading.value = false
  }
}

function addSeason() {
  const form = newSeasonForm.value
  const existing = seasons.value.find((s: any) => s.season_number === form.season_number)
  const ids: Record<string, any> = {}
  if (form.imdb_id) ids.imdb_id = form.imdb_id
  if (form.tvdb_id) ids.tvdb_id = form.tvdb_id
  if (form.douban_id) ids.douban_id = form.douban_id
  if (form.bgm_id) ids.bgm_id = form.bgm_id
  if (existing) {
    existing.external_ids = { ...existing.external_ids, ...ids }
  } else {
    seasons.value.push({ season_number: form.season_number, external_ids: ids })
  }
  newSeasonForm.value = { season_number: form.season_number + 1, imdb_id: '', tvdb_id: null, douban_id: null, bgm_id: '' }
}

function removeSeason(index: number) {
  seasons.value.splice(index, 1)
}

function normalizeBgmId(bgmId: string): string {
  return bgmId.replace(/，/g, ',').replace(/、/g, ',').replace(/;/g, ',').replace(/；/g, ',').split(',').map(id => id.trim()).filter(Boolean).join(',')
}

async function saveExternalIds() {
  externalIdsLoading.value = true
  try {
    const dataToSave: any = { external_ids: { ...mainExternalIds.value } }
    if (dataToSave.external_ids.bgm_id) {
      dataToSave.external_ids.bgm_id = normalizeBgmId(dataToSave.external_ids.bgm_id)
    }
    const filteredSeasons = seasons.value.filter((s: any) => Object.keys(s.external_ids).length > 0)
    if (filteredSeasons.length > 0) {
      dataToSave.seasons = filteredSeasons.map((s: any) => ({
        season_number: s.season_number,
        external_ids: {
          ...s.external_ids,
          bgm_id: s.external_ids.bgm_id ? normalizeBgmId(s.external_ids.bgm_id) : s.external_ids.bgm_id
        }
      }))
    }
    await api.put(`/api/items/${store.currentItemType}/${store.currentItemId}/externalids`, dataToSave)
    notify('外部ID保存成功', '', 'success')
    showExternalIds.value = false
    await store.loadDetails()
  } catch (e: any) {
    notify('保存失败', e.message, 'error')
  } finally {
    externalIdsLoading.value = false
  }
}

watch(showExternalIds, (v) => { if (v) loadExternalIds() })

function applyExternalIdsJson(parsed: any) {
  if (parsed.external_ids !== undefined && (!parsed.external_ids || typeof parsed.external_ids !== 'object' || Array.isArray(parsed.external_ids))) {
    notify('JSON 格式错误', 'external_ids 字段必须是对象', 'error')
    return
  }
  if (parsed.seasons !== undefined && !Array.isArray(parsed.seasons)) {
    notify('JSON 格式错误', 'seasons 字段必须是数组', 'error')
    return
  }
  const newSeasons: any[] = parsed.seasons || []
  for (const season of newSeasons) {
    if (!season || typeof season !== 'object') {
      notify('JSON 格式错误', 'seasons 内的每一项必须是对象', 'error')
      return
    }
    if (!season.external_ids || typeof season.external_ids !== 'object') season.external_ids = {}
  }
  mainExternalIds.value = parsed.external_ids || {}
  seasons.value = newSeasons
  showExternalIdsJson.value = false
  notify('JSON 已应用', '需点击底部保存以生效', 'success')
}

// 特别篇弹框
const showSpecialEpisode = ref(false)

// 剧集组弹框
const showEpisodeGroup = ref(false)

// 删除元数据文件弹框
const showDeleteFiles = ref(false)
const deleteLoading = ref(false)
const deleteTargets = ref<string[]>([])

const deleteTargetOptions = computed(() => {
  const options = [
    { title: '元数据 JSON 文件', value: 'metadata', subtitle: '主 JSON 及季/集 JSON' },
    { title: '标签文件', value: 'tags', subtitle: '自定义标签 JSON' },
    { title: '外部ID文件', value: 'external_ids', subtitle: 'IMDB/TVDB/豆瓣/BGM ID' },
  ]
  if (!isMovie.value) {
    options.push(
      { title: '特别篇插入', value: 'episode_order', subtitle: '剧集排列顺序' },
      { title: '剧集组文件', value: 'episode_group', subtitle: '剧集分组配置' },
    )
  }
  return options
})

function toggleDeleteTarget(value: string) {
  const idx = deleteTargets.value.indexOf(value)
  if (idx >= 0) deleteTargets.value.splice(idx, 1)
  else deleteTargets.value.push(value)
}

async function handleDeleteFiles() {
  if (deleteTargets.value.length === 0) {
    notify('请至少选择一个要删除的项目', '', 'warning')
    return
  }
  const labels = deleteTargets.value.map(v => deleteTargetOptions.value.find(o => o.value === v)?.title).join('、')
  const ok = await confirm({ title: '最终确认', content: `即将删除：${labels}\n此操作不可恢复，确定要继续吗？`, confirmColor: 'error' })
  if (!ok) return
  deleteLoading.value = true
  try {
    const success = await store.deleteSelectedFiles(deleteTargets.value)
    if (success) { notify('删除成功', '', 'success'); showDeleteFiles.value = false; deleteTargets.value = [] }
    else notify('删除失败', '', 'error')
  } finally {
    deleteLoading.value = false
  }
}

// 操作分组
const actionGroups = computed(() => {
  const groups: { title: string; items: { key: string; title: string; subtitle: string; icon: string; color?: string }[] }[] = []

  groups.push({
    title: '数据更新',
    items: [
      { key: 'updateFromTmdb', title: '从 TMDB 更新', subtitle: '选择字段和语言', icon: 'mdi-movie-search', color: 'info' },
      { key: 'updateFromBangumi', title: '从 Bangumi 更新', subtitle: '选择字段和模式', icon: 'mdi-cloud-download', color: 'info' },
      { key: 'updateFromEmby', title: '从 Emby 更新', subtitle: '从 Emby 拉取元数据', icon: 'mdi-sync', color: 'info' },
      { key: 'refreshCache', title: '刷新缓存', subtitle: '重新扫描本地 JSON 并更新数据库', icon: 'mdi-refresh', color: 'info' },
      { key: 'copyToOverride', title: '补充到 Override', subtitle: '将缓存数据复制为 Override', icon: 'mdi-content-copy', color: 'info' },
      { key: 'lockName', title: '锁定名称', subtitle: '将名称锁定到 Patches 文件', icon: 'mdi-lock', color: 'info' },
      { key: 'generateTags', title: '生成自定义标签', subtitle: '根据元数据自动生成标签', icon: 'mdi-tag-plus', color: 'info' },
    ],
  })

  const toolItems: any[] = [
    { key: 'jsonEditor', title: '编辑原始 JSON', subtitle: '直接修改元数据 JSON', icon: 'mdi-code-block-braces', color: 'secondary' },
    { key: 'exportZip', title: '导出数据 (Zip)', subtitle: '下载 Override 数据包', icon: 'mdi-download', color: 'secondary' },
    { key: 'manageBackups', title: '备份管理', subtitle: '创建和恢复备份', icon: 'mdi-backup-restore', color: 'secondary' },
    { key: 'manageExternalIds', title: '外部ID管理', subtitle: 'IMDB/TVDB/豆瓣/BGM', icon: 'mdi-link-variant', color: 'secondary' },
  ]

  if (!isMovie.value) {
    toolItems.push(
      { key: 'manageSpecialEpisodes', title: '特别篇插入', subtitle: '管理特别篇的排列顺序', icon: 'mdi-playlist-play', color: 'secondary' },
      { key: 'manageEpisodeGroups', title: '剧集组', subtitle: '管理剧集分组', icon: 'mdi-group', color: 'secondary' },
    )
  }

  groups.push({ title: '工具', items: toolItems })

  const deleteItems: any[] = [
    { key: 'deleteImages', title: '删除所有图片', subtitle: '不可恢复', icon: 'mdi-image-remove', color: 'error' },
    { key: 'deletePatches', title: '删除 Patches 文件夹', subtitle: '不可恢复', icon: 'mdi-folder-remove-outline', color: 'error' },
    { key: 'deleteFiles', title: '删除元数据文件', subtitle: '多选删除 Override 中的 JSON 文件', icon: 'mdi-file-remove', color: 'error' },
  ]

  deleteItems.push(
    { key: 'deleteOverride', title: '删除 Override 文件夹', subtitle: '不可恢复！将删除整个 Override 目录', icon: 'mdi-folder-remove', color: 'error' },
    { key: 'deleteCache', title: '删除 Cache 文件夹', subtitle: '不可恢复！将删除主缓存', icon: 'mdi-folder-remove', color: 'error' },
  )

  groups.push({ title: '危险操作', items: deleteItems })

  return groups
})

async function handleAction(key: string) {
  // 弹框类操作
  if (key === 'updateFromTmdb') { showTmdbUpdate.value = true; return }
  if (key === 'updateFromBangumi') { showBangumiUpdate.value = true; return }
  if (key === 'updateFromEmby') { showEmbyUpdate.value = true; return }
  if (key === 'manageBackups') { showBackupManager.value = true; return }
  if (key === 'manageExternalIds') { showExternalIds.value = true; return }
  if (key === 'deleteFiles') { showDeleteFiles.value = true; deleteTargets.value = []; return }
  if (key === 'manageSpecialEpisodes') { showSpecialEpisode.value = true; return }
  if (key === 'manageEpisodeGroups') { showEpisodeGroup.value = true; return }

  if (key === 'lockName') {
    const runLock = async () => {
      const success = await store.lockName()
      if (success) notify('操作成功', '', 'success')
      else notify('操作失败', '', 'error')
    }
    await runLock()
    return
  }

  if (key === 'generateTags') {
    pendingAction.value = key
    selectedMode.value = 'merge'
    showModeDialog.value = true
    return
  }

  const runAction = async () => {
    let success = false
    switch (key) {
      case 'refreshCache': await store.refreshCache(); success = true; break
      case 'copyToOverride': success = await store.copyItemToOverride(); break
      case 'embyRefresh': await store.triggerEmbyRefresh(); success = true; break
      case 'jsonEditor': editingJsonData.value = store.itemDetails?.full_metadata || {}; showJsonEditor.value = true; return
      case 'exportZip': { const token = localStorage.getItem('access_token'); const baseUrl = import.meta.env.VITE_API_BASE_URL || ''; const url = `${baseUrl}/api/items/${store.currentItemType}/${store.currentItemId}/export_zip${token ? '?auth_token=' + encodeURIComponent(token) : ''}`; window.open(url, '_blank'); return }
      case 'deleteImages': success = await store.deleteImages(); break
      case 'deletePatches': success = await store.deletePatches(); break
      case 'deleteOverride': success = await store.deleteOverrideFolder(); break
      case 'deleteCache': success = await store.deleteCacheFolder(); break
    }
    if (success) notify('操作成功', '', 'success')
    else if (key !== 'jsonEditor' && key !== 'exportZip') notify('操作失败', '', 'error')
  }

  if (key.startsWith('delete')) {
    const ok = await confirm({ title: '删除确认', content: '此操作不可恢复，确定要继续吗？', confirmColor: 'error' })
    if (ok) await runAction()
  } else {
    await runAction()
  }
}

async function handleModeConfirm() {
  showModeDialog.value = false
  let success = false
  if (pendingAction.value === 'generateTags') success = await store.generateTags(selectedMode.value)
  if (success) notify('操作成功', '', 'success')
  else notify('操作失败', '', 'error')
}

async function handleSaveJson(data: any) {
  try {
    const success = await store.saveMetadata(data)
    if (success) { notify('JSON 保存成功', '', 'success'); showJsonEditor.value = false }
    else notify('保存失败', '', 'error')
  } catch (e: any) {
    notify('保存失败', e.message, 'error')
  }
}
</script>

<template>
  <v-container fluid>
    <v-card v-for="group in actionGroups" :key="group.title" class="pa-4 mb-4" variant="outlined">
      <div class="text-subtitle-2 font-weight-bold mb-3">{{ group.title }}</div>
      <v-row>
        <v-col v-for="item in group.items" :key="item.key" cols="12" sm="6">
          <!-- 玻璃主题下 v-card tonal 彩色会出现 underlay 色块（设计系统只处理了 v-btn 的 tonal 彩色），
               操作项统一用 outlined 卡 + 彩色图标，颜色语义保留在图标上 -->
          <v-card
            variant="outlined"
            rounded="lg"
            hover
            class="hover-lift"
            @click="handleAction(item.key)"
          >
            <v-list-item>
              <template #prepend>
                <v-icon :icon="item.icon" :color="item.color" />
              </template>
              <v-list-item-title class="text-body-2">{{ item.title }}</v-list-item-title>
              <v-list-item-subtitle>{{ item.subtitle }}</v-list-item-subtitle>
            </v-list-item>
          </v-card>
        </v-col>
      </v-row>
    </v-card>

    <!-- 模式选择对话框 -->
    <v-dialog v-model="showModeDialog" max-width="380">
      <v-card rounded="xl">
        <v-card-title>选择模式</v-card-title>
        <v-card-text>
          <v-radio-group v-model="selectedMode">
            <v-radio label="合并 (Merge) - 保留已有数据" value="merge" />
            <v-radio label="覆盖 (Overwrite) - 替换所有数据" value="overwrite" />
          </v-radio-group>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showModeDialog = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-check" @click="handleModeConfirm">确认</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- JSON 编辑器 -->
    <JsonEditorDialog
      v-model="showJsonEditor"
      :initial-data="editingJsonData"
      :loading="store.isLoading"
      @confirm="handleSaveJson"
    />

    <!-- TMDB 更新对话框 -->
    <v-dialog v-model="showTmdbUpdate" max-width="620" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-movie-search" class="mr-2" />
          从 TMDB 更新元数据
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showTmdbUpdate = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <!-- 语言选择 -->
          <v-select v-model="tmdbLang" :items="langOptions" label="TMDB 语言" density="compact" variant="outlined" class="mb-3" />

          <!-- 更新目标 (仅 TV) -->
          <template v-if="!isMovie">
            <div class="text-subtitle-2 font-weight-bold mb-2">更新目标</div>
            <v-radio-group v-model="tmdbUpdateTarget" density="compact" class="mb-2" hide-details>
              <v-radio label="仅剧集信息 (Series Only)" value="series_only" />
              <v-radio label="整部剧集 (All Seasons & Episodes)" value="whole_series" />
              <v-radio label="特定季 (Season)" value="season" />
              <v-radio label="特定集 (Episode)" value="episode" />
            </v-radio-group>

            <!-- 季号/集号输入 -->
            <v-row v-if="tmdbUpdateTarget === 'season' || tmdbUpdateTarget === 'episode'" density="compact" class="mb-2">
              <v-col cols="6">
                <v-text-field v-model.number="tmdbTargetSeason" type="number" label="季号" density="compact" variant="outlined" hide-details />
              </v-col>
              <v-col v-if="tmdbUpdateTarget === 'episode'" cols="6">
                <v-text-field v-model.number="tmdbTargetEpisode" type="number" label="集号" density="compact" variant="outlined" hide-details />
              </v-col>
            </v-row>

            <!-- 特定季时，可选择同时更新该季所有分集 -->
            <v-switch v-if="tmdbUpdateTarget === 'season'" v-model="tmdbUpdateSeasonEpisodes" label="同时更新该季所有分集" density="compact" hide-details color="primary" class="mb-3" />
          </template>

          <v-divider class="my-3" />

          <!-- 字段选择 -->
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-2 font-weight-bold">更新字段选择</span>
            <v-spacer />
            <v-btn size="small" variant="tonal" @click="selectAllTmdbFields">全选</v-btn>
            <v-btn size="small" variant="tonal" @click="deselectAllTmdbFields">清空</v-btn>
          </div>
          <v-select v-model="tmdbFields" :items="tmdbAvailableFields" multiple chips label="更新字段"
            density="compact" variant="outlined" class="mb-3" />

          <v-divider class="my-3" />

          <!-- 选项 -->
          <div class="d-flex align-center mb-2">
            <v-switch v-model="tmdbOverwrite" label="覆盖现有数据" density="compact" hide-details color="primary" />
            <v-tooltip max-width="300">
              <template #activator="{ props }">
                <v-icon v-bind="props" size="18" class="ml-1">mdi-help-circle-outline</v-icon>
              </template>
              如果开启，TMDB 返回的数据将完全覆盖所选字段的现有内容。如果关闭，仅补充缺失数据(部分字段支持)。通常建议开启。
            </v-tooltip>
          </div>
          <v-switch v-model="tmdbTriggerEmbyRefresh" label="触发 Emby 刷新" density="compact" hide-details color="primary" />
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showTmdbUpdate = false">取消</v-btn>
          <v-btn color="info" variant="tonal" prepend-icon="mdi-refresh" :loading="tmdbLoading" @click="handleTmdbUpdate">开始更新</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Bangumi 更新对话框 -->
    <v-dialog v-model="showBangumiUpdate" max-width="600" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-cloud-download" class="mr-2" />
          从 Bangumi 更新元数据
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showBangumiUpdate = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <!-- 推荐加载中 -->
          <div v-if="bangumiRecommendLoading" class="text-center pa-4">
            <v-progress-circular indeterminate color="info" size="small" />
            <span class="ml-2 text-medium-emphasis">正在获取 Bangumi 关联推荐...</span>
          </div>

          <template v-else>
            <!-- 推荐状态 -->
            <v-alert v-if="bangumiStatus === 'none'" type="warning" variant="tonal" density="compact" class="mb-3">
              未找到匹配的 Bangumi 条目，请手动输入 ID。
            </v-alert>
            <v-alert v-else-if="bangumiStatus === 'linked'" type="success" variant="tonal" density="compact" class="mb-3">
              <div>已关联 Bangumi ID: <strong>{{ bangumiId }}</strong> ({{ bangumiTitle }})</div>
              <div class="mt-1">
                <v-chip size="x-small" color="success" variant="tonal" class="mr-1">{{ getBgmTypeName(bangumiType) }}</v-chip>
                <v-chip v-if="bangumiPlatform" size="x-small" color="info" variant="tonal" class="mr-1">{{ bangumiPlatform }}</v-chip>
                <v-chip v-if="bangumiYear" size="x-small" color="warning" variant="tonal" class="mr-1">{{ bangumiYear }}</v-chip>
                <v-chip v-if="bangumiSource" size="x-small" variant="tonal" class="mr-1">{{ bangumiSource }}</v-chip>
              </div>
            </v-alert>
            <v-alert v-else-if="bangumiStatus === 'recommended'" type="info" variant="tonal" density="compact" class="mb-3">
              <div>推荐关联 Bangumi ID: <strong>{{ bangumiId }}</strong> ({{ bangumiTitle }}) - 匹配度 {{ bangumiScore?.toFixed(1) }}</div>
              <div class="mt-1">
                <v-chip size="x-small" color="success" variant="tonal" class="mr-1">{{ getBgmTypeName(bangumiType) }}</v-chip>
                <v-chip v-if="bangumiPlatform" size="x-small" color="info" variant="tonal" class="mr-1">{{ bangumiPlatform }}</v-chip>
                <v-chip v-if="bangumiYear" size="x-small" color="warning" variant="tonal" class="mr-1">{{ bangumiYear }}</v-chip>
              </div>
            </v-alert>

            <!-- Bangumi ID 输入 -->
            <v-text-field v-model.number="bangumiId" type="number" label="Bangumi ID" placeholder="请输入 Bangumi Subject ID"
              density="compact" variant="outlined" class="mb-3" hide-details />

            <!-- 强制刷新缓存 -->
            <v-switch v-model="bangumiForceRefresh" label="强制刷新缓存" density="compact" hide-details color="primary" class="mb-2"
              hint="忽略本地缓存，直接从 Bangumi API 拉取最新数据" persistent-hint />

            <v-divider class="my-3" />

            <!-- 字段选择 -->
            <div class="d-flex align-center mb-2">
              <span class="text-subtitle-2 font-weight-bold">更新字段选择</span>
              <v-spacer />
              <v-btn size="small" variant="tonal" @click="selectAllBangumiFields">全选</v-btn>
              <v-btn size="small" variant="tonal" @click="deselectAllBangumiFields">清空</v-btn>
            </div>
            <v-select v-model="bangumiFields" :items="bangumiFieldOptions" multiple chips label="更新字段"
              density="compact" variant="outlined" class="mb-3" />

            <!-- 高级选项 -->
            <div class="text-subtitle-2 font-weight-bold mb-2">高级选项</div>
            <v-select v-model="bangumiMode" :items="[{title:'合并 (保留现有数据，仅追加)',value:'merge'},{title:'覆盖 (完全替换选中字段)',value:'overwrite'}]"
              label="模式" density="compact" variant="outlined" class="mb-3" />
            <v-checkbox v-model="bangumiUseWhitelist" label="使用全局标签白名单 (仅针对标签)" density="compact" hide-details />
          </template>
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showBangumiUpdate = false">取消</v-btn>
          <v-btn color="info" variant="tonal" prepend-icon="mdi-refresh" :loading="bangumiLoading" :disabled="!bangumiId || bangumiRecommendLoading" @click="handleBangumiUpdate">更新元数据</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Emby 更新对话框 -->
    <v-dialog v-model="showEmbyUpdate" max-width="560" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-sync" class="mr-2" />
          从 Emby 更新元数据
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showEmbyUpdate = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-select v-model="embyFields" :items="embyFieldOptions" multiple chips label="更新字段"
            density="compact" variant="outlined" class="mb-3" />
          <v-switch v-model="embyUpdateChildren" label="更新子项 (季/集)" density="compact" hide-details color="primary" />
          <v-select v-if="embyUpdateChildren" v-model="embyChildFields" :items="embyChildFieldOptions" multiple chips
            label="子项更新字段" density="compact" variant="outlined" class="mt-2" />
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showEmbyUpdate = false">取消</v-btn>
          <v-btn color="success" variant="tonal" prepend-icon="mdi-refresh" :loading="embyLoading" @click="handleEmbyUpdate">开始更新</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 备份管理对话框 -->
    <v-dialog v-model="showBackupManager" max-width="500" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-backup-restore" class="mr-2" />
          备份管理
          <v-spacer />
          <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="handleCreateBackup">创建备份</v-btn>
          <v-btn icon="mdi-close" variant="text" size="small" @click="showBackupManager = false" class="ml-2" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <div v-if="backupLoading" class="text-center pa-4">
            <v-progress-circular indeterminate color="primary" />
          </div>
          <v-list v-else-if="backups.length" density="compact">
            <v-list-item v-for="b in backups" :key="b.name" class="mb-1" rounded="xl">
              <v-list-item-title>{{ b.name }}</v-list-item-title>
              <v-list-item-subtitle v-if="b.size">{{ (b.size / 1024).toFixed(1) }} KB</v-list-item-subtitle>
              <template #append>
                <v-btn size="x-small" variant="tonal" color="warning" class="mr-1" @click="handleRestoreBackup(b.name)">恢复</v-btn>
                <v-btn size="x-small" variant="tonal" color="error" @click="handleDeleteBackup(b.name)">删除</v-btn>
              </template>
            </v-list-item>
          </v-list>
          <div v-else class="text-center pa-4 text-medium-emphasis">
            <v-icon size="48" color="grey-lighten-1">mdi-backup-restore</v-icon>
            <p class="mt-2">暂无备份</p>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>

    <!-- 外部ID管理对话框 -->
    <v-dialog v-model="showExternalIds" max-width="700" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-link-variant" class="mr-2" />
          编辑外部ID
          <v-spacer />
          <v-tooltip location="top">
            <template #activator="{ props }">
              <v-btn v-bind="props" icon="mdi-code-block-braces" variant="text" size="small" :disabled="externalIdsLoading" @click="showExternalIdsJson = true" />
            </template>
            编辑原始 JSON
          </v-tooltip>
          <v-btn icon="mdi-close" variant="text" size="small" @click="showExternalIds = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <div v-if="externalIdsLoading" class="text-center pa-4">
            <v-progress-circular indeterminate color="primary" />
          </div>
          <template v-else>
            <!-- 主条目外部ID -->
            <div class="text-subtitle-2 font-weight-bold mb-3">主条目外部ID</div>
            <v-row density="compact">
              <v-col cols="6">
                <v-text-field v-model="mainExternalIds.imdb_id" label="IMDB ID" placeholder="例如: tt9335498" density="compact" variant="outlined" clearable hide-details />
              </v-col>
              <v-col cols="6">
                <v-text-field v-model="mainExternalIds.tvdb_id" label="TVDB ID" placeholder="数字ID" density="compact" variant="outlined" clearable hide-details />
              </v-col>
              <v-col cols="6">
                <v-text-field v-model="mainExternalIds.douban_id" label="豆瓣 ID" placeholder="数字ID" density="compact" variant="outlined" clearable hide-details />
              </v-col>
              <v-col cols="6">
                <v-text-field v-model="mainExternalIds.bgm_id" label="BGM ID" placeholder="逗号分隔多个，如: 369768,123456" density="compact" variant="outlined" clearable hide-details />
              </v-col>
            </v-row>

            <!-- 季度外部ID（仅电视剧） -->
            <template v-if="!isMovie">
              <v-divider class="my-4" />
              <div class="text-subtitle-2 font-weight-bold mb-3">添加季度外部ID</div>
              <v-card variant="outlined" rounded="xl" class="pa-3 mb-4">
                <div class="control-row">
                  <v-text-field v-model.number="newSeasonForm.season_number" label="季号" type="number" density="compact" variant="outlined" hide-details class="mw-110px" />
                  <v-text-field v-model="newSeasonForm.imdb_id" label="IMDB ID" density="compact" variant="outlined" clearable hide-details class="mw-140px" />
                  <v-text-field v-model="newSeasonForm.tvdb_id" label="TVDB ID" density="compact" variant="outlined" clearable hide-details class="mw-140px" />
                  <v-text-field v-model="newSeasonForm.douban_id" label="豆瓣 ID" density="compact" variant="outlined" clearable hide-details class="mw-140px" />
                  <v-text-field v-model="newSeasonForm.bgm_id" label="BGM ID" placeholder="逗号分隔多个，如: 369768,123456" density="compact" variant="outlined" clearable hide-details class="miw-160px flex-1" />
                  <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-plus" @click="addSeason">添加/更新</v-btn>
                </div>
              </v-card>

              <!-- 已有季度列表 -->
              <template v-if="seasons.length">
                <div class="text-subtitle-2 font-weight-bold mt-2 mb-2">已有季度 ({{ seasons.length }})</div>
                <v-card v-for="(season, index) in seasons" :key="index" variant="outlined" rounded="xl" class="pa-3 mb-2">
                  <div class="d-flex align-center mb-2">
                    <v-chip size="small" color="primary" variant="tonal" label>第 {{ season.season_number }} 季</v-chip>
                    <v-spacer />
                    <v-btn size="small" variant="tonal" color="error" icon="mdi-close" @click="removeSeason(index)" />
                  </div>
                  <div class="d-flex flex-wrap ga-1">
                    <v-chip v-if="season.external_ids?.imdb_id" size="small" variant="tonal" label color="info">
                      <v-icon start size="x-small">mdi-open-in-new</v-icon>IMDB: {{ season.external_ids.imdb_id }}
                    </v-chip>
                    <v-chip v-if="season.external_ids?.tvdb_id" size="small" variant="tonal" label color="info">TVDB: {{ season.external_ids.tvdb_id }}</v-chip>
                    <v-chip v-if="season.external_ids?.douban_id" size="small" variant="tonal" label color="success">豆瓣: {{ season.external_ids.douban_id }}</v-chip>
                    <v-chip v-if="season.external_ids?.bgm_id" size="small" variant="tonal" label color="warning">BGM: {{ season.external_ids.bgm_id }}</v-chip>
                    <span v-if="!season.external_ids || !Object.keys(season.external_ids).length" class="text-caption text-medium-emphasis">无外部ID</span>
                  </div>
                </v-card>
              </template>
          </template>
          </template>
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showExternalIds = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-check" :loading="externalIdsLoading" @click="saveExternalIds">保存</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 外部ID原始 JSON 编辑 -->
    <JsonEditorDialog
      v-model="showExternalIdsJson"
      :initial-data="{ external_ids: mainExternalIds, seasons: seasons }"
      confirm-text="确定"
      hint="点击「确定」后应用到表单，需再点击「保存」才会写入文件"
      @confirm="applyExternalIdsJson"
    />

    <!-- 特别篇插入 -->
    <SpecialEpisodeModal
      v-model="showSpecialEpisode"
      :series-id="store.currentItemId"
      :series-name="store.itemDetails?.name || store.itemDetails?.full_metadata?.name || ''"
      @refresh="store.loadDetails()"
    />

    <!-- 剧集组 -->
    <EpisodeGroupModal
      v-model="showEpisodeGroup"
      :series-id="store.currentItemId"
      :series-name="store.itemDetails?.name || store.itemDetails?.full_metadata?.name || ''"
      @refresh="store.loadDetails()"
    />

    <!-- 删除元数据文件对话框 -->
    <v-dialog v-model="showDeleteFiles" max-width="500">
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-file-remove" class="mr-2" />
          删除元数据文件
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showDeleteFiles = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-alert type="warning" variant="tonal" density="compact" class="mb-3">
            选择要删除的 Override 文件，此操作不可恢复。
          </v-alert>
          <div class="d-flex align-center mb-2">
            <span class="text-subtitle-2 font-weight-bold">选择删除项</span>
            <v-spacer />
            <v-btn size="small" variant="tonal" @click="deleteTargets = deleteTargetOptions.map(o => o.value)">全选</v-btn>
            <v-btn size="small" variant="tonal" class="ml-1" @click="deleteTargets = []">清空</v-btn>
          </div>
          <v-list density="compact" class="pa-0">
            <v-list-item v-for="opt in deleteTargetOptions" :key="opt.value" @click="toggleDeleteTarget(opt.value)" rounded="lg" class="mb-1">
              <template #prepend>
                <v-checkbox-btn :model-value="deleteTargets.includes(opt.value)" hide-details color="error" @click.stop="toggleDeleteTarget(opt.value)" />
              </template>
              <v-list-item-title class="text-body-2">{{ opt.title }}</v-list-item-title>
              <v-list-item-subtitle class="text-caption text-medium-emphasis">{{ opt.subtitle }}</v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showDeleteFiles = false">取消</v-btn>
          <v-btn color="error" variant="tonal" prepend-icon="mdi-delete" :loading="deleteLoading" :disabled="deleteTargets.length === 0" @click="handleDeleteFiles">下一步</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

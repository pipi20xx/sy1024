<script setup lang="ts">
import { onMounted, onUnmounted, onActivated, onDeactivated, ref, computed, watch, nextTick } from 'vue'
defineOptions({ name: 'HomeView' })
import { useItemStore, useSystemStore, useWorkflowStore } from '@/stores'
import MediaGrid from '@/components/media/MediaGrid.vue'
import FilterBar from '@/components/media/FilterBar.vue'
import GenerateOverrideModal from '@/components/home/GenerateOverrideModal.vue'
import ContentRatingModal from '@/components/home/ContentRatingModal.vue'
import SpecifyScrapeModal from '@/components/home/SpecifyScrapeModal.vue'
import { triggerScan, getScanStatus, importOverrideZip } from '@/api/system'
import { useNotification, useConfirm } from '@/composables'
import type { WorkflowTask } from '@/api/workflow'

const itemStore = useItemStore()
const systemStore = useSystemStore()
const workflowStore = useWorkflowStore()
const { notify } = useNotification()
const { confirm } = useConfirm()

const isScanning = ref(false)
const scanText = ref('扫描库')
const fileInput = ref<HTMLInputElement | null>(null)
const showWorkflowDialog = ref(false)
const showGenerateOverride = ref(false)
const showContentRating = ref(false)
const showSpecifyScrape = ref(false)
const selectedTasks = ref<WorkflowTask[]>([])
const workflowInterval = ref(2)

const isMovie = computed(() => itemStore.currentItemType === 'tmdb-movies2')
const itemTypeLabel = computed(() => isMovie.value ? '电影' : '电视剧')

// 滚动位置保存/恢复：离开页面时保存，回来时恢复
let _savedScrollTop = 0

// 文件监控自动刷新（2秒防抖）
let _fwReloadTimer: ReturnType<typeof setTimeout> | null = null
watch(() => systemStore.fileWatcherTimestamp, (ts) => {
  if (!ts) return
  if (_fwReloadTimer) clearTimeout(_fwReloadTimer)
  _fwReloadTimer = setTimeout(() => {
    // 只刷新第一页，保留用户当前所在页面的基础数据
    itemStore.loadItems(itemStore.currentItemType)
    itemStore.loadAvailableFilters(itemStore.currentItemType)
  }, 2000)
})

onMounted(() => {
  if (itemStore.items.length === 0) {
    itemStore.loadItems(itemStore.currentItemType)
  }
  itemStore.loadAvailableFilters(itemStore.currentItemType)
  window.addEventListener('scroll', handleScroll, true)
})

// keep-alive: 激活时恢复滚动位置 + 重新注册滚动监听
onActivated(() => {
  window.addEventListener('scroll', handleScroll, true)
  // 恢复滚动位置（nextTick 确保 DOM 已渲染）
  nextTick(() => {
    window.scrollTo(0, _savedScrollTop)
  })
})

// keep-alive: 停用时保存滚动位置 + 移除滚动监听
onDeactivated(() => {
  _savedScrollTop = window.scrollY || document.documentElement.scrollTop || 0
  window.removeEventListener('scroll', handleScroll, true)
})

onUnmounted(() => {
  window.removeEventListener('scroll', handleScroll, true)
  // 清理文件监控防抖定时器
  if (_fwReloadTimer) { clearTimeout(_fwReloadTimer); _fwReloadTimer = null }
})

function handleScroll(event?: Event) {
  let scrollTop = 0, clientHeight = 0, scrollHeight = 0
  if (event?.target && event.target !== document && event.target !== window) {
    const target = event.target as HTMLElement
    scrollTop = target.scrollTop; clientHeight = target.clientHeight; scrollHeight = target.scrollHeight
  } else {
    scrollTop = document.documentElement.scrollTop || document.body.scrollTop
    clientHeight = window.innerHeight
    scrollHeight = document.documentElement.scrollHeight || document.body.scrollHeight
  }
  if (scrollTop + clientHeight >= scrollHeight - 300 && itemStore.hasNextPage && !itemStore.isLoading) {
    itemStore.loadMoreItems()
  }
}

async function handleScan() {
  if (isScanning.value) return
  const ok = await confirm({
    title: '确认扫描',
    content: '扫描的是本地元数据缓存目录，需要提前设置好路径。',
    confirmColor: 'primary',
  })
  if (!ok) return
  isScanning.value = true; scanText.value = '启动中...'
  try {
    await triggerScan()
    const poll = setInterval(async () => {
      try {
        const status = await getScanStatus()
        if (status.status === 'scanning') {
          const percent = status.total > 0 ? Math.round((status.current / status.total) * 100) : 0
          scanText.value = `扫描中 ${percent}%`
        } else {
          clearInterval(poll); isScanning.value = false; scanText.value = '扫描库'
          if (status.status === 'completed') {
            notify('扫描完成', `共处理 ${status.total} 个项目`, 'success')
            itemStore.loadItems(itemStore.currentItemType)
            itemStore.loadAvailableFilters(itemStore.currentItemType)
          } else {
            notify('扫描失败', status.message, 'error')
          }
        }
      } catch (e) { /* continue polling */ }
    }, 1000)
    // 安全兜底：10 分钟后自动清除轮询，防止因异常导致 interval 泄漏
    setTimeout(() => { if (isScanning.value) { clearInterval(poll); isScanning.value = false; scanText.value = '扫描库' } }, 600000)
  } catch (e: any) {
    isScanning.value = false; scanText.value = '扫描库'
    notify('启动扫描失败', e.message, 'error')
  }
}

function triggerImport() { fileInput.value?.click() }

async function handleImport(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) return
  const files = Array.from(target.files)
  let successCount = 0, failCount = 0
  for (const file of files) {
    try {
      const result = await importOverrideZip(file)
      if (result.success) successCount++; else failCount++
    } catch { failCount++ }
  }
  if (failCount === 0) notify('导入成功', `成功导入 ${successCount} 个文件`, 'success')
  else notify('导入完成', `${successCount} 成功, ${failCount} 失败`, 'warning')
  if (successCount > 0) itemStore.loadItems(itemStore.currentItemType)
  target.value = ''
}

// 工作流相关
const baseFields = [
  { title: '标题 (Title/Name)', value: 'title' },
  { title: '原始标题 (Original Title)', value: 'original_title' },
  { title: '简介 (Overview)', value: 'overview' },
  { title: '类型 (Genres)', value: 'genres' },
  { title: '标签 (Tags)', value: 'tags' },
  { title: '标语 (Tagline)', value: 'tagline' },
  { title: '首播/上映日期', value: 'air_date' },
  { title: '完结日期', value: 'end_date' },
  { title: '评分 (Vote Average)', value: 'vote_average' },
]

const childFields = [
  { title: '季名称', value: 'season_name' },
  { title: '季简介', value: 'season_overview' },
  { title: '季播出年份', value: 'season_air_date' },
  { title: '集标题', value: 'episode_name' },
  { title: '集简介', value: 'episode_overview' },
  { title: '集播出日期', value: 'episode_air_date' },
]

const tmdbMovieFields = [
  { title: '标题', value: 'title' },
  { title: '原始标题', value: 'original_title' },
  { title: '简介', value: 'overview' },
  { title: '评分', value: 'vote_average' },
  { title: '上映日期', value: 'release_date' },
  { title: '时长', value: 'runtime' },
  { title: '标语', value: 'tagline' },
  { title: '类型', value: 'genres' },
  { title: '演职员', value: 'casts' },
  { title: '制作公司', value: 'production_companies' },
  { title: '关键词', value: 'keywords' },
  { title: '语言', value: 'spoken_languages' },
]

const tmdbTvFields = [
  { title: '名称', value: 'name' },
  { title: '原始名称', value: 'original_name' },
  { title: '简介', value: 'overview' },
  { title: '标语', value: 'tagline' },
  { title: '评分', value: 'vote_average' },
  { title: '首播日期', value: 'first_air_date' },
  { title: '最新日期', value: 'last_air_date' },
  { title: '状态', value: 'status' },
  { title: '类型', value: 'genres' },
  { title: '演职员', value: 'casts' },
  { title: '制作公司', value: 'production_companies' },
  { title: '电视网', value: 'networks' },
  { title: '关键词', value: 'keywords' },
  { title: '语言列表', value: 'languages' },
]

const tmdbChildFields = [
  { title: '名称', value: 'name' },
  { title: '简介', value: 'overview' },
  { title: '评分', value: 'vote_average' },
  { title: '播出日期', value: 'air_date' },
  { title: '时长 (集)', value: 'runtime' },
  { title: '演职员', value: 'casts' },
  { title: '预告片', value: 'trailers' },
]

const bangumiFields = [
  { title: '标题 (中文)', value: 'title' },
  { title: '原名', value: 'original_title' },
  { title: '简介', value: 'overview' },
  { title: '标签 (Tags)', value: 'tags' },
  { title: '评分 (Rating)', value: 'vote_average' },
  { title: '日期 (Date)', value: 'release_date' },
]

const languageOptions = [
  { title: '简体中文 (zh-CN)', value: 'zh-CN' },
  { title: '繁体中文 (zh-TW)', value: 'zh-TW' },
  { title: '英语 (en-US)', value: 'en-US' },
  { title: '日语 (ja-JP)', value: 'ja-JP' },
  { title: '韩语 (ko-KR)', value: 'ko-KR' },
]

const tmdbFields = computed(() => isMovie.value ? tmdbMovieFields : tmdbTvFields)

function handleAddTask(task: WorkflowTask) {
  const newTask = JSON.parse(JSON.stringify(task))

  if (newTask.type === 'emby_update_metadata') {
    if (!newTask.params) newTask.params = {}
    if (!newTask.params.fields_to_update) newTask.params.fields_to_update = baseFields.map(f => f.value)
    if (newTask.params.update_children === undefined) newTask.params.update_children = false
    if (!newTask.params.child_fields) newTask.params.child_fields = childFields.map(f => f.value)
  }

  if (newTask.type === 'tmdb_update_metadata') {
    if (!newTask.params) newTask.params = {}
    newTask.params.fields_to_update = tmdbFields.value.map(f => f.value)
    newTask.params.overwrite = true
    newTask.params.trigger_emby_refresh = false
    newTask.params.lang = 'zh-CN'
    if (!isMovie.value) {
      newTask.params.update_season_episodes = false
      newTask.params.child_fields = tmdbChildFields.map(f => f.value)
    }
  }

  if (newTask.type === 'bangumi_update_metadata') {
    if (!newTask.params) newTask.params = {}
    newTask.params.fields_to_update = ['title', 'overview', 'tags', 'vote_average']
    if (newTask.params.force_refresh === undefined) newTask.params.force_refresh = false
    if (newTask.params.use_whitelist === undefined) newTask.params.use_whitelist = false
    if (newTask.params.mode === undefined) newTask.params.mode = 'merge'
    if (newTask.params.auto_match === undefined) newTask.params.auto_match = false
  }

  if (newTask.type === 'download_web_images') {
    if (!newTask.params) newTask.params = {}
    if (!newTask.params.sources) newTask.params.sources = ['tmdb', 'fanart']
    if (!newTask.params.image_types) newTask.params.image_types = ['poster', 'fanart', 'logo']
    if (!newTask.params.behavior) newTask.params.behavior = 'overwrite'
    if (!newTask.params.lang_priority) newTask.params.lang_priority = 'zh'
  }

  if (newTask.type === 'ai_translate') {
    newTask.params = {
      title: true, overview: true, season_title: false, season_overview: false,
      episode_title: false, episode_overview: false, credits: false,
      include_children_credits: false,
      credits_options: { cast_name: true, cast_character: true, crew_name: false, crew_job: false },
    }
  }

  selectedTasks.value.push(newTask)
}

function handleRemoveTask(index: number) {
  selectedTasks.value.splice(index, 1)
}

function handleClearTasks() {
  selectedTasks.value = []
}

function moveUp(index: number) {
  if (index > 0) {
    const item = selectedTasks.value.splice(index, 1)[0]
    selectedTasks.value.splice(index - 1, 0, item)
  }
}

function moveDown(index: number) {
  if (index < selectedTasks.value.length - 1) {
    const item = selectedTasks.value.splice(index, 1)[0]
    selectedTasks.value.splice(index + 1, 0, item)
  }
}

function getTaskIcon(type: string): string {
  if (type === 'ai_translate') return 'mdi-translate'
  if (type === 'tmdb_update_metadata') return 'mdi-magnify'
  if (type === 'bangumi_update_metadata') return 'mdi-cloud-download'
  if (type === 'copy_to_override') return 'mdi-content-copy'
  if (type === 'emby_download_images') return 'mdi-image-multiple'
  if (type === 'emby_update_metadata' || type === 'emby_refresh') return 'mdi-sync'
  if (type === 'lock_name') return 'mdi-lock'
  if (type.startsWith('delete')) return 'mdi-delete'
  if (type.includes('tags')) return 'mdi-tag-multiple'
  return 'mdi-puzzle'
}

async function handleExecuteWorkflow() {
  if (selectedTasks.value.length === 0) {
    notify('提示', '请至少添加一个任务', 'warning')
    return
  }

  const ok = await confirm({
    title: '确认执行工作流',
    content: `将对当前筛选条件下的 ${itemStore.total} 个${itemTypeLabel.value}执行 ${selectedTasks.value.length} 个任务，间隔 ${workflowInterval.value} 秒。`,
    confirmColor: 'warning',
  })
  if (!ok) return

  const tasksToRun = selectedTasks.value.map(task => {
    const t = JSON.parse(JSON.stringify(task))
    if (t.type === 'emby_update_metadata' && t.params.update_children && t.params.child_fields) {
      t.params.fields_to_update = [...(t.params.fields_to_update || []), ...t.params.child_fields]
      delete t.params.child_fields
    }
    if (t.type === 'tmdb_update_metadata' && t.params.update_season_episodes && t.params.child_fields) {
      t.params.fields_to_update = [...(t.params.fields_to_update || []), ...t.params.child_fields]
      delete t.params.child_fields
    }
    return t
  })

  const success = await workflowStore.executeWorkflow(tasksToRun, workflowInterval.value)
  if (success) {
    notify('工作流已启动', '', 'success')
    showWorkflowDialog.value = false
    selectedTasks.value = []
  } else {
    notify('工作流启动失败', '', 'error')
  }
}
</script>

<template>
  <v-container fluid class="pa-6">
    <!-- 顶栏：类型切换 + 操作按钮 -->
    <div class="d-flex flex-wrap align-center mb-3 ga-3">
      <!-- 类型切换：与详情页 TAB 一致的 v-tabs 样式，选中仅文字变主题色 -->
      <v-tabs :model-value="itemStore.currentItemType" color="primary" @update:model-value="itemStore.setCurrentItemType($event)">
        <v-tab value="tmdb-tv">
          <v-icon start>mdi-television-classic</v-icon>
          电视剧
        </v-tab>
        <v-tab value="tmdb-movies2">
          <v-icon start>mdi-movie-open</v-icon>
          电影
        </v-tab>
      </v-tabs>
      <v-spacer />
      <div class="d-flex ga-2 flex-wrap">
        <v-btn color="warning" :loading="isScanning" @click="handleScan" size="small" variant="tonal">
          <v-icon start>mdi-magnify-scan</v-icon>
          {{ scanText }}
        </v-btn>
        <v-btn color="info" size="small" variant="tonal" rounded="xl" @click="triggerImport">
          <v-icon start>mdi-import</v-icon>
          导入数据
        </v-btn>
        <v-btn color="success" size="small" variant="tonal" rounded="xl" @click="showWorkflowDialog = true">
          <v-icon start>mdi-lightning-bolt</v-icon>
          工作流
        </v-btn>
        <v-btn color="warning" size="small" variant="tonal" rounded="xl" @click="showGenerateOverride = true">
          <v-icon start>mdi-flash</v-icon>
          一键生成
        </v-btn>
        <v-btn class="glass-btn" color="accent" size="small" variant="tonal" @click="showContentRating = true">
          <v-icon start>mdi-shield-star</v-icon>
          分级管理
        </v-btn>
        <v-btn class="glass-btn" color="primary" size="small" variant="tonal" @click="showSpecifyScrape = true">
          <v-icon start>mdi-target-account</v-icon>
          指定刮削
        </v-btn>
        <input type="file" ref="fileInput" @change="handleImport" accept=".zip" multiple class="d-none" />
      </div>
    </div>

    <!-- 筛选栏 -->
    <FilterBar />

    <!-- 媒体网格 -->
    <MediaGrid :items="itemStore.items" />

    <!-- 加载中 -->
    <div v-if="itemStore.isLoading" class="text-center pa-6">
      <v-progress-circular indeterminate color="primary" size="48" />
      <p class="mt-2 text-medium-emphasis">加载中...</p>
    </div>

    <!-- 加载失败 -->
    <div v-if="itemStore.error" class="text-center pa-6">
      <v-icon size="64" color="error">mdi-alert-circle</v-icon>
      <p class="mt-2 text-error">{{ itemStore.error }}</p>
      <v-btn size="small" color="primary" @click="itemStore.loadItems(itemStore.currentItemType, itemStore.currentPage)">重试</v-btn>
    </div>

    <!-- 没有更多 -->
    <div v-if="!itemStore.hasNextPage && !itemStore.isLoading && itemStore.items.length > 0" class="text-center pa-4 text-medium-emphasis">
      <v-divider class="mb-4" />
      没有更多了
    </div>

    <!-- 空列表 -->
    <div v-if="!itemStore.isLoading && itemStore.items.length === 0 && !itemStore.error" class="text-center pa-8">
      <v-icon size="80" color="grey">mdi-movie-open-off-outline</v-icon>
      <p class="mt-4 text-h6 text-medium-emphasis">未找到任何项目</p>
      <p class="text-body-2 text-medium-emphasis">请尝试调整筛选条件或扫描数据</p>
    </div>

    <!-- 工作流对话框 - 完整版 -->
    <v-dialog v-model="showWorkflowDialog" max-width="950" scrollable>
      <v-card rounded="xl">
        <!-- 头部 -->
        <v-card-title class="d-flex align-center pa-4">
          <v-icon icon="mdi-lightning-bolt" class="mr-2" />
          批量操作工作流
          <v-spacer />
          <div class="d-flex align-center ga-2">
            <v-chip size="small" variant="tonal" color="primary">{{ itemTypeLabel }}</v-chip>
            <v-chip size="small" variant="tonal" color="success">{{ itemStore.total }} 个项目</v-chip>
            <v-btn icon="mdi-close" variant="text" size="small" @click="showWorkflowDialog = false" />
          </div>
        </v-card-title>
        <v-divider />

        <!-- 主体 - 左右分栏 -->
        <v-card-text class="pa-0 workflow-panel">
          <v-row no-gutters class="h-100">
            <!-- 左侧 - 可用任务 -->
            <v-col cols="5" class="border-e h-100 scroll-y">
              <div class="pa-3 text-subtitle-2 font-weight-bold d-flex align-center">
                <v-icon start size="small">mdi-format-list-bulleted</v-icon>
                可用任务库
                <span class="text-caption text-medium-emphasis ml-2">(点击添加)</span>
              </div>
              <v-divider />
              <v-list density="compact" class="pa-2">
                <v-list-item
                  v-for="task in workflowStore.availableTasks"
                  :key="task.type"
                  @click="handleAddTask(task)"
                  rounded="xl"
                  class="mb-1"
                >
                  <template #prepend>
                    <v-icon :icon="getTaskIcon(task.type)" size="small" class="mr-2" />
                  </template>
                  <v-list-item-title class="text-body-2">{{ task.description }}</v-list-item-title>
                  <v-list-item-subtitle class="text-caption text-medium-emphasis">{{ task.type }}</v-list-item-subtitle>
                </v-list-item>
              </v-list>
            </v-col>

            <!-- 右侧 - 执行队列 -->
            <v-col cols="7" class="h-100 scroll-y">
              <div class="pa-3 text-subtitle-2 font-weight-bold d-flex align-center">
                <v-icon start size="small">mdi-playlist-play</v-icon>
                执行队列
                <span class="text-caption text-medium-emphasis ml-2">按顺序执行</span>
                <v-spacer />
                <v-btn v-if="selectedTasks.length > 0" size="small" variant="tonal" color="error" @click="handleClearTasks">清空</v-btn>
              </div>
              <v-divider />

              <div v-if="selectedTasks.length === 0" class="text-center pa-8">
                <v-icon size="48" color="grey-lighten-1">mdi-playlist-remove</v-icon>
                <p class="mt-2 text-medium-emphasis">队列为空，请从左侧添加任务</p>
              </div>

              <div v-else class="pa-3">
                <v-card v-for="(task, index) in selectedTasks" :key="index" variant="outlined" rounded="xl" class="mb-3 pa-3">
                  <div class="d-flex align-center mb-2">
                    <v-chip size="x-small" variant="flat" color="primary" class="mr-2">{{ index + 1 }}</v-chip>
                    <v-icon :icon="getTaskIcon(task.type)" size="small" class="mr-2" />
                    <span class="font-weight-medium text-body-2">{{ task.description }}</span>
                    <v-spacer />
                    <v-btn size="small" variant="tonal" icon="mdi-chevron-up" @click="moveUp(index)" :disabled="index === 0" />
                    <v-btn size="small" variant="tonal" icon="mdi-chevron-down" @click="moveDown(index)" :disabled="index === selectedTasks.length - 1" />
                    <v-btn size="small" variant="tonal" icon="mdi-close" color="error" @click="handleRemoveTask(index)" />
                  </div>

                  <!-- 参数配置区域 -->
                  <div v-if="task.params && Object.keys(task.params).length > 0" class="ml-4 mt-2 pa-3 workflow-task-params">
                    <!-- Download Web Images Config -->
                    <div v-if="task.type === 'download_web_images'">
                      <div class="text-caption text-medium-emphasis mb-1">来源:</div>
                      <div class="d-flex ga-2 mb-2">
                        <v-checkbox v-model="task.params.sources" value="tmdb" label="TMDb" density="compact" hide-details />
                        <v-checkbox v-model="task.params.sources" value="fanart" label="Fanart" density="compact" hide-details />
                      </div>
                      <div class="text-caption text-medium-emphasis mb-1">类型:</div>
                      <div class="d-flex flex-wrap ga-2 mb-2">
                        <v-checkbox v-model="task.params.image_types" value="poster" label="海报" density="compact" hide-details />
                        <v-checkbox v-model="task.params.image_types" value="fanart" label="背景" density="compact" hide-details />
                        <v-checkbox v-model="task.params.image_types" value="logo" label="Logo" density="compact" hide-details />
                        <v-checkbox v-model="task.params.image_types" value="clearart" label="艺术图" density="compact" hide-details />
                        <v-checkbox v-model="task.params.image_types" value="thumb" label="缩略图" density="compact" hide-details />
                        <v-checkbox v-model="task.params.image_types" value="banner" label="横幅" density="compact" hide-details />
                        <v-checkbox v-model="task.params.image_types" value="disc" label="光盘" density="compact" hide-details />
                      </div>
                      <v-row density="compact">
                        <v-col cols="4">
                          <v-select v-model="task.params.behavior" :items="[{title:'覆盖',value:'overwrite'},{title:'跳过',value:'skip'}]" label="模式" density="compact" variant="outlined" hide-details />
                        </v-col>
                        <v-col cols="4">
                          <v-select v-model="task.params.lang_priority" :items="[{title:'中文 (zh)',value:'zh'},{title:'英文 (en)',value:'en'},{title:'无偏好',value:''}]" label="优先语言" density="compact" variant="outlined" hide-details />
                        </v-col>
                      </v-row>
                    </div>

                    <!-- Emby Update Metadata Config -->
                    <div v-if="task.type === 'emby_update_metadata'">
                      <div class="text-caption text-medium-emphasis mb-1">主信息字段:</div>
                      <v-select v-model="task.params.fields_to_update" :items="baseFields" multiple chips density="compact" variant="outlined" hide-details class="mb-2" />
                      <v-checkbox v-model="task.params.update_children" label="更新子项 (季/集)" density="compact" hide-details />
                      <template v-if="task.params.update_children">
                        <div class="text-caption text-medium-emphasis mb-1 mt-2">子项字段:</div>
                        <v-select v-model="task.params.child_fields" :items="childFields" multiple chips density="compact" variant="outlined" hide-details />
                      </template>
                    </div>

                    <!-- TMDB Update Metadata Config -->
                    <div v-if="task.type === 'tmdb_update_metadata'">
                      <v-select v-model="task.params.lang" :items="languageOptions" label="语言" density="compact" variant="outlined" hide-details class="mb-2" />
                      <div class="text-caption text-medium-emphasis mb-1">更新字段:</div>
                      <v-select v-model="task.params.fields_to_update" :items="tmdbFields" multiple chips density="compact" variant="outlined" hide-details class="mb-2" />
                      <div class="d-flex ga-2">
                        <v-checkbox v-model="task.params.overwrite" label="覆盖现有" density="compact" hide-details />
                        <v-checkbox v-model="task.params.trigger_emby_refresh" label="刷新Emby" density="compact" hide-details />
                      </div>
                      <v-checkbox v-if="!isMovie" v-model="task.params.update_season_episodes" label="同时更新所有季/集" density="compact" hide-details />
                      <template v-if="task.params.update_season_episodes">
                        <div class="text-caption text-medium-emphasis mb-1 mt-2">季/集字段:</div>
                        <v-select v-model="task.params.child_fields" :items="tmdbChildFields" multiple chips density="compact" variant="outlined" hide-details />
                      </template>
                    </div>

                    <!-- Bangumi Update Metadata Config -->
                    <div v-if="task.type === 'bangumi_update_metadata'">
                      <div class="text-caption text-medium-emphasis mb-1">更新字段:</div>
                      <v-select v-model="task.params.fields_to_update" :items="bangumiFields" multiple chips density="compact" variant="outlined" hide-details class="mb-2" />
                      <v-select v-model="task.params.mode" :items="[{title:'合并 (保留现有)',value:'merge'},{title:'覆盖 (完全替换)',value:'overwrite'}]" label="模式" density="compact" variant="outlined" hide-details class="mb-2" />
                      <div class="d-flex ga-2">
                        <v-checkbox v-model="task.params.use_whitelist" label="标签白名单" density="compact" hide-details />
                        <v-checkbox v-model="task.params.force_refresh" label="强制刷新缓存" density="compact" hide-details />
                      </div>
                      <v-checkbox v-model="task.params.auto_match" label="自动匹配缺失关联 (推荐)" density="compact" hide-details color="success" />
                    </div>

                    <!-- Lock Name Config -->
                    <div v-if="task.type === 'lock_name'">
                      <div class="text-caption text-medium-emphasis">将当前名称写入 patches 文件，无需选择模式</div>
                    </div>

                    <!-- Delete Override Files Config -->
                    <div v-if="task.type === 'delete_override_files'">
                      <v-select v-model="task.params.targets" :items="[
                        { title: '元数据 JSON', value: 'metadata' },
                        { title: '标签文件', value: 'tags' },
                        { title: '外部ID文件', value: 'external_ids' },
                        { title: '特别篇插入', value: 'episode_order' },
                        { title: '剧集组文件', value: 'episode_group' },
                      ]" multiple chips label="删除目标" density="compact" variant="outlined" hide-details />
                    </div>

                    <!-- AI Translate Config -->
                    <div v-if="task.type === 'ai_translate'">
                      <div class="text-caption text-medium-emphasis mb-1">翻译内容选择:</div>
                      <div class="d-flex flex-wrap ga-2 mb-2">
                        <v-checkbox v-model="task.params.title" label="标题" density="compact" hide-details />
                        <v-checkbox v-model="task.params.overview" label="简介" density="compact" hide-details />
                        <template v-if="!isMovie">
                          <v-checkbox v-model="task.params.season_title" label="季标题" density="compact" hide-details />
                          <v-checkbox v-model="task.params.season_overview" label="季简介" density="compact" hide-details />
                          <v-checkbox v-model="task.params.episode_title" label="集标题" density="compact" hide-details />
                          <v-checkbox v-model="task.params.episode_overview" label="集简介" density="compact" hide-details />
                        </template>
                        <v-checkbox v-model="task.params.credits" label="演职员" density="compact" hide-details />
                      </div>
                      <div v-if="task.params.credits" class="pa-2 border rounded bg-surface mt-2">
                        <div class="text-caption text-success font-weight-bold mb-1">演职员翻译细节:</div>
                        <v-checkbox v-if="!isMovie" v-model="task.params.include_children_credits" label="包含所有季/集演职员" density="compact" hide-details />
                        <div class="d-flex flex-wrap ga-2">
                          <v-checkbox v-model="task.params.credits_options.cast_name" label="演员姓名" density="compact" hide-details />
                          <v-checkbox v-model="task.params.credits_options.cast_character" label="角色名" density="compact" hide-details />
                          <v-checkbox v-model="task.params.credits_options.crew_name" label="制作人姓名" density="compact" hide-details />
                          <v-checkbox v-model="task.params.credits_options.crew_job" label="职位" density="compact" hide-details />
                        </div>
                      </div>
                    </div>
                  </div>
                </v-card>
              </div>
            </v-col>
          </v-row>
        </v-card-text>

        <v-divider />
        <!-- 底部操作栏 -->
        <v-card-actions class="pa-4">
          <div class="text-caption text-medium-emphasis">* 所有任务将在后台异步执行</div>
          <v-spacer />
          <div class="d-flex align-center ga-3">
            <v-text-field v-model.number="workflowInterval" label="间隔(秒)" type="number" min="0" step="0.5" density="compact" variant="outlined" hide-details class="w-100px" />
            <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showWorkflowDialog = false">取消</v-btn>
            <v-btn
              color="accent"
              variant="tonal"
              :loading="workflowStore.isLoading"
              :disabled="selectedTasks.length === 0"
              @click="handleExecuteWorkflow"
              prepend-icon="mdi-play"
            >
              执行工作流
            </v-btn>
          </div>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 首页弹框组件 -->
    <GenerateOverrideModal v-model="showGenerateOverride" />
    <ContentRatingModal v-model="showContentRating" />
    <SpecifyScrapeModal v-model="showSpecifyScrape" />
  </v-container>
</template>

<style scoped>
/* 工作流编排面板：固定高度，内部两栏各自滚动 */
.workflow-panel {
  height: 500px;
  overflow: hidden;
}
</style>

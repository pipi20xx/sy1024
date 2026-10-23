<script setup lang="ts">
import { onMounted, ref, watch, computed } from 'vue'
import { tasksApi, type ScheduledTask } from '@/api/tasks'
defineOptions({ name: 'TasksView' })
import { getAvailableFonts } from '@/api/collectionPoster'
import { api } from '@/api/client'
import { useNotification, useConfirm } from '@/composables'

const { notify } = useNotification()
const { confirm } = useConfirm()

const tasks = ref<ScheduledTask[]>([])
const isLoading = ref(false)
const showDialog = ref(false)
const isEditing = ref(false)
const editingId = ref<number | undefined>()

// ======== 简易定时模式 ========
const scheduleMode = ref<'simple' | 'advanced'>('simple')
const simpleSchedule = ref({
  type: 'daily' as 'daily' | 'weekly' | 'hourly' | 'interval',
  hour: 3,
  minute: 0,
  dayOfWeek: 1,
  intervalHours: 6,
})

const hourOptions = Array.from({ length: 24 }, (_, i) => ({ title: `${i} 时`, value: i }))
const minuteOptions = Array.from({ length: 60 }, (_, i) => ({ title: `${i} 分`, value: i }))
const dayOptions = [
  { title: '周一', value: 1 },
  { title: '周二', value: 2 },
  { title: '周三', value: 3 },
  { title: '周四', value: 4 },
  { title: '周五', value: 5 },
  { title: '周六', value: 6 },
  { title: '周日', value: 0 },
]

watch(simpleSchedule, (val) => {
  if (scheduleMode.value === 'simple') {
    if (val.type === 'daily') {
      form.value.cron_expression = `${val.minute} ${val.hour} * * *`
    } else if (val.type === 'weekly') {
      form.value.cron_expression = `${val.minute} ${val.hour} * * ${val.dayOfWeek}`
    } else if (val.type === 'hourly') {
      form.value.cron_expression = '0 * * * *'
    } else if (val.type === 'interval') {
      form.value.cron_expression = `0 */${val.intervalHours} * * *`
    }
  }
}, { deep: true })

// ======== 字体 & 媒体库 ========
const fonts = ref<{ title: string; value: string }[]>([])
const libraries = ref<{ title: string; value: string }[]>([])

async function loadMetadata() {
  try {
    const [resFonts, resLibs] = await Promise.all([
      getAvailableFonts(),
      api.get<{ libraries: { Id: string; Name: string }[] }>('/api/covers/libraries'),
    ])
    fonts.value = (resFonts.fonts || []).map((f: string) => ({ title: f, value: f }))
    libraries.value = (resLibs.libraries || []).map((l: any) => ({ title: l.Name, value: l.Id }))
  } catch (e) {
    console.error('加载字体/媒体库元数据失败', e)
  }
}

// ======== 任务类型 ========
const taskTypeOptions = [
  { title: 'EMBY 封面生成器', value: 'cover' },
  { title: '合集海报批量生成', value: 'collection_poster' },
  { title: 'Bangumi-Data 映射表同步', value: 'bangumi_data_sync' },
  { title: 'Bangumi 映射同步到 Emby', value: 'bangumi_sync' },
  { title: '系统自动备份', value: 'backup' },
  { title: '预览图定期清理', value: 'preview_cleanup' },
  { title: '扫描媒体库', value: 'scan_library' },
  { title: '工作流', value: 'workflow' },
]

const taskTypeLabel = (type: string) => {
  const opt = taskTypeOptions.find(o => o.value === type)
  return opt ? opt.title : type
}

// ======== 封面样式 & 合集样式选项 ========
const styleOptionsCovers = [
  { title: '单图样式 1', value: 'single_1' },
  { title: '单图样式 2', value: 'single_2' },
  { title: '多图九宫格', value: 'multi_1' },
  { title: '多图九宫格(动态)', value: 'multi_animated' },
  { title: '背景轮播 (动态)', value: 'style_6_plus_1' },
  { title: '背景斜播 (动态)', value: 'style_9_plus_1' },
  { title: '横向轮播 (动态)', value: 'style_5_horizontal' },
]

const styleOptionsCollections = [
  { title: '圆环聚焦 (Circle Focus)', value: 'circle_focus' },
  { title: '扇形排列 (Fan)', value: 'fan' },
  { title: '单图封面 (Single)', value: 'single' },
  { title: '流媒体英雄 (Streaming Hero)', value: 'streaming_hero' },
  { title: '撕纸效果 (Torn Paper)', value: 'torn_paper' },
  { title: '水墨丹青 (Ink Brush)', value: 'ink_brush' },
  { title: '3D悬浮 (3D Float)', value: '3d_float' },
  { title: '赛博故障 (Cyber Glitch)', value: 'cyber_glitch' },
]

const resolutionOptions = [
  { title: '1x (标准)', value: 1.0 },
  { title: '1.5x (高清)', value: 1.5 },
  { title: '2x (超清)', value: 2.0 },
  { title: '4x (极致)', value: 4.0 },
]

// ======== 表单 ========
const defaultForm = (): Partial<ScheduledTask> => ({
  name: '',
  task_type: 'cover',
  cron_expression: '0 3 * * *',
  enabled: true,
  params: '{}',
})

const form = ref(defaultForm())

// 解析 params JSON 为响应式对象
const taskParams = ref<Record<string, any>>({})

function resetParamsForType(type: string) {
  if (type === 'cover') {
    taskParams.value = {
      library_ids: [],
      style_type: 'single_1',
      upload: true,
      font_zh: fonts.value[0]?.value || '',
      font_en: fonts.value[0]?.value || '',
      zh_font_size_ratio: 1.0,
      en_font_size_ratio: 1.0,
      blur_size: 50,
      color_ratio: 0.8,
      sort_by: 'Random',
      is_blur: false,
      title_config: '',
      use_primary_first: false,
      animation_format: 'png',
    }
  } else if (type === 'collection_poster') {
    taskParams.value = {
      collection_names_str: '',
      style_type: 'circle_focus',
      font_zh: fonts.value[0]?.value || '',
      font_en: fonts.value[0]?.value || '',
      zh_font_size_ratio: 1.0,
      en_font_size_ratio: 1.0,
      offset_x: 0,
      offset_y: 0,
      resolution_scale: 1.0,
      show_zh: true,
      show_en: true,
    }
  } else if (type === 'bangumi_data_sync') {
    taskParams.value = {}
  } else if (type === 'bangumi_sync') {
    taskParams.value = {
      item_types: 'Movie,Series',
      is_preview: false,
      write_to_genres: false,
      write_to_tags: true,
      is_merge_mode: true,
    }
  } else if (type === 'backup') {
    taskParams.value = {
      mode: 'snapshot',
      include_override: true,
      include_collections: true,
    }
  } else if (type === 'preview_cleanup') {
    taskParams.value = {
      max_age_hours: 24,
    }
  } else if (type === 'scan_library') {
    taskParams.value = {}
  } else if (type === 'workflow') {
    taskParams.value = {
      item_type: 'tmdb-tv',
      tasks: [],
      interval_seconds: 2,
    }
  }
}

const isAnimatedCoverStyle = computed(() =>
  ['multi_animated', 'style_6_plus_1', 'style_9_plus_1', 'style_5_horizontal'].includes(taskParams.value.style_type)
)

// ======== 工作流步骤选项 ========
const workflowStepOptions = [
  { title: '从网络下载图片', value: 'download_web_images' },
  { title: '从 Emby 下载图片', value: 'emby_download_images' },
  { title: '补充到 Override', value: 'copy_to_override' },
  { title: '从 Emby 更新元数据', value: 'emby_update_metadata' },
  { title: '从 TMDB 更新元数据', value: 'tmdb_update_metadata' },
  { title: '从 Bangumi 更新元数据', value: 'bangumi_update_metadata' },
  { title: 'AI 批量中文化', value: 'ai_translate' },
  { title: '生成自定义标签', value: 'generate_item_tags' },
  { title: 'Emby 刷新', value: 'emby_refresh' },
  { title: '删除 Override (慎用)', value: 'delete_override' },
  { title: '删除所有图片', value: 'delete_all_images' },
  { title: '删除元数据文件', value: 'delete_override_files' },
  { title: '锁定名称', value: 'lock_name' },
]

// 工作流步骤字段选项
const wfBaseFields = [
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

const wfChildFields = [
  { title: '季名称', value: 'season_name' },
  { title: '季简介', value: 'season_overview' },
  { title: '季播出年份', value: 'season_air_date' },
  { title: '集标题', value: 'episode_name' },
  { title: '集简介', value: 'episode_overview' },
  { title: '集播出日期', value: 'episode_air_date' },
]

const wfTmdbMovieFields = [
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

const wfTmdbTvFields = [
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

const wfTmdbChildFields = [
  { title: '名称', value: 'name' },
  { title: '简介', value: 'overview' },
  { title: '评分', value: 'vote_average' },
  { title: '播出日期', value: 'air_date' },
  { title: '时长 (集)', value: 'runtime' },
  { title: '演职员', value: 'casts' },
  { title: '预告片', value: 'trailers' },
]

const wfBangumiFields = [
  { title: '标题 (中文)', value: 'title' },
  { title: '原名', value: 'original_title' },
  { title: '简介', value: 'overview' },
  { title: '标签 (Tags)', value: 'tags' },
  { title: '评分 (Rating)', value: 'vote_average' },
  { title: '日期 (Date)', value: 'release_date' },
]

const wfLanguageOptions = [
  { title: '简体中文 (zh-CN)', value: 'zh-CN' },
  { title: '繁体中文 (zh-TW)', value: 'zh-TW' },
  { title: '英语 (en-US)', value: 'en-US' },
  { title: '日语 (ja-JP)', value: 'ja-JP' },
  { title: '韩语 (ko-KR)', value: 'ko-KR' },
]

const isWfMovie = computed(() => taskParams.value.item_type === 'tmdb-movies2')
const wfTmdbFields = computed(() => isWfMovie.value ? wfTmdbMovieFields : wfTmdbTvFields)

// 工作流步骤是否有可配置参数
const wfStepHasParams = (type: string) => [
  'download_web_images', 'emby_update_metadata', 'tmdb_update_metadata',
  'bangumi_update_metadata', 'ai_translate', 'delete_override_files',
].includes(type)

// 初始化工作流步骤的默认参数
function initWfStepParams(type: string): Record<string, any> {
  switch (type) {
    case 'download_web_images':
      return { sources: ['tmdb', 'fanart'], image_types: ['poster', 'fanart', 'logo'], behavior: 'overwrite', lang_priority: 'zh' }
    case 'emby_update_metadata':
      return { fields_to_update: wfBaseFields.map(f => f.value), update_children: false, child_fields: wfChildFields.map(f => f.value) }
    case 'tmdb_update_metadata': {
      const p: Record<string, any> = {
        fields_to_update: wfTmdbFields.value.map(f => f.value),
        overwrite: true, trigger_emby_refresh: false, lang: 'zh-CN',
      }
      if (!isWfMovie.value) {
        p.update_season_episodes = false
        p.child_fields = wfTmdbChildFields.map(f => f.value)
      }
      return p
    }
    case 'bangumi_update_metadata':
      return { fields_to_update: ['title', 'overview', 'tags', 'vote_average'], force_refresh: false, use_whitelist: false, mode: 'merge', auto_match: false }
    case 'ai_translate':
      return {
        title: true, overview: true, season_title: false, season_overview: false,
        episode_title: false, episode_overview: false, credits: false,
        include_children_credits: false,
        credits_options: { cast_name: true, cast_character: true, crew_name: false, crew_job: false },
      }
case 'lock_name':
return {}
case 'delete_override_files':
  return { targets: ['metadata', 'tags', 'external_ids', 'episode_order', 'episode_group'] }
    default:
      return {}
  }
}

function addWorkflowStep() {
  if (!taskParams.value.tasks) taskParams.value.tasks = []
  const type = 'download_web_images'
  taskParams.value.tasks.push({ type, params: initWfStepParams(type) })
}

// 步骤类型变更时重新初始化参数
function onWfStepTypeChange(step: { type: string; params: Record<string, any> }) {
  step.params = initWfStepParams(step.type)
}

// 保存前处理：合并 child_fields 到 fields_to_update
function processWfTasksBeforeSave(tasks: any[]) {
  return tasks.map((t: any) => {
    const cloned = JSON.parse(JSON.stringify(t))
    if (cloned.type === 'emby_update_metadata' && cloned.params.update_children && cloned.params.child_fields) {
      cloned.params.fields_to_update = [...(cloned.params.fields_to_update || []), ...cloned.params.child_fields]
      delete cloned.params.child_fields
    }
    if (cloned.type === 'tmdb_update_metadata' && cloned.params.update_season_episodes && cloned.params.child_fields) {
      cloned.params.fields_to_update = [...(cloned.params.fields_to_update || []), ...cloned.params.child_fields]
      delete cloned.params.child_fields
    }
    return cloned
  })
}

// ======== 生命周期 ========
onMounted(async () => {
  await loadMetadata()
  loadTasks()
})

async function loadTasks() {
  isLoading.value = true
  try { tasks.value = await tasksApi.getTasks() }
  catch (e: any) { notify('加载失败', e.message, 'error') }
  finally { isLoading.value = false }
}

// ======== 操作 ========
function openAdd() {
  isEditing.value = false
  editingId.value = undefined
  form.value = defaultForm()
  scheduleMode.value = 'simple'
  simpleSchedule.value = { type: 'daily', hour: 3, minute: 0, dayOfWeek: 1, intervalHours: 6 }
  resetParamsForType('cover')
  showDialog.value = true
}

function openEdit(task: ScheduledTask) {
  isEditing.value = true
  editingId.value = task.id
  form.value = {
    name: task.name,
    task_type: task.task_type,
    cron_expression: task.cron_expression,
    enabled: task.enabled,
    params: task.params,
  }
  try {
    taskParams.value = JSON.parse(task.params)
  } catch {
    taskParams.value = {}
  }

  // 尝试反向解析 cron 为简易模式
  const parts = task.cron_expression.split(' ')
  if (parts.length === 5) {
    const [m, h, d, mo, dw] = parts
    if (d === '*' && mo === '*' && dw === '*') {
      simpleSchedule.value.type = 'daily'
      simpleSchedule.value.hour = parseInt(h) || 0
      simpleSchedule.value.minute = parseInt(m) || 0
      scheduleMode.value = 'simple'
    } else if (d === '*' && mo === '*' && dw !== '*') {
      simpleSchedule.value.type = 'weekly'
      simpleSchedule.value.hour = parseInt(h) || 0
      simpleSchedule.value.minute = parseInt(m) || 0
      simpleSchedule.value.dayOfWeek = parseInt(dw) || 0
      scheduleMode.value = 'simple'
    } else if (m === '0' && h.startsWith('*/')) {
      simpleSchedule.value.type = 'interval'
      simpleSchedule.value.intervalHours = parseInt(h.replace('*/', '')) || 6
      scheduleMode.value = 'simple'
    } else {
      scheduleMode.value = 'advanced'
    }
  } else {
    scheduleMode.value = 'advanced'
  }

  showDialog.value = true
}

async function handleSave() {
  if (!form.value.name || !form.value.task_type || !form.value.cron_expression) {
    notify('提示', '名称、类型和 Cron 表达式不能为空', 'warning')
    return
  }
  try {
    const payload = {
      ...form.value,
      params: JSON.stringify(taskParams.value),
    }
    if (isEditing.value && editingId.value) {
      await tasksApi.updateTask(editingId.value, payload)
      notify('更新成功', '', 'success')
    } else {
      await tasksApi.createTask(payload)
      notify('创建成功', '', 'success')
    }
    showDialog.value = false
    await loadTasks()
  } catch (e: any) {
    notify('保存失败', e.message, 'error')
  }
}

async function handleDelete(id: number, name: string) {
  const ok = await confirm({
    title: '删除任务',
    content: `确认删除定时任务「${name}」？`,
    confirmColor: 'error',
  })
  if (!ok) return
  try {
    await tasksApi.deleteTask(id)
    notify('已删除', '', 'success')
    await loadTasks()
  } catch (e: any) {
    notify('删除失败', e.message, 'error')
  }
}

async function handleToggle(task: ScheduledTask) {
  try {
    await tasksApi.updateTask(task.id, { enabled: task.enabled })
    notify(task.enabled ? '已启用' : '已禁用', '', 'success')
  } catch (e: any) {
    task.enabled = !task.enabled
    notify('操作失败', e.message, 'error')
  }
}

async function handleRun(id: number) {
  try {
    await tasksApi.runTask(id)
    notify('任务已触发', '', 'success')
    setTimeout(() => loadTasks(), 2000)
  } catch (e: any) {
    notify('触发失败', e.message, 'error')
  }
}

function onTaskTypeChange(val: string) {
  resetParamsForType(val)
}

function formatDate(d: string | null) {
  if (!d) return '—'
  return d.length >= 19 ? d.substring(0, 19).replace('T', ' ') : d
}
</script>

<template>
  <v-container fluid class="pa-6">
    <!-- 页头 -->
    <div class="d-flex flex-wrap align-center mb-6 ga-3">
      <div class="flex-grow-1">
        <h1 class="text-h5 font-weight-bold">定时任务</h1>
        <p class="text-caption text-medium-emphasis mt-1">
          管理自动执行的定时任务 · 共 {{ tasks.length }} 个任务
        </p>
      </div>
      <div class="d-flex ga-2 flex-wrap">
        <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-plus" @click="openAdd">
          新建任务
        </v-btn>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="isLoading && !tasks.length" class="text-center pa-8">
      <v-progress-circular indeterminate color="primary" size="40" />
      <p class="mt-3 text-medium-emphasis">加载中...</p>
    </div>

    <!-- 任务卡片 -->
    <v-row v-if="tasks.length" density="compact">
      <v-col v-for="task in tasks" :key="task.id" cols="12" sm="6" md="4">
        <v-card variant="outlined" rounded="xl" class="pa-4 h-100">
          <div class="d-flex align-center mb-2">
            <v-icon :icon="task.enabled ? 'mdi-clock-check-outline' : 'mdi-clock-remove-outline'" class="mr-2" />
            <span class="text-subtitle-2 font-weight-bold flex-grow-1">{{ task.name }}</span>
            <v-switch v-model="task.enabled" density="compact" hide-details color="success"
              @update:model-value="handleToggle(task)" />
          </div>

          <v-chip size="x-small" variant="tonal" label class="mb-2">{{ taskTypeLabel(task.task_type) }}</v-chip>

          <div class="text-caption text-medium-emphasis">
            <div><v-icon size="x-small" start>mdi-clock-outline</v-icon>Cron: <code>{{ task.cron_expression }}</code></div>
            <div v-if="task.last_run"><v-icon size="x-small" start>mdi-check</v-icon>上次运行: {{ formatDate(task.last_run) }}</div>
            <div v-if="task.next_run"><v-icon size="x-small" start>mdi-arrow-right</v-icon>下次运行: {{ formatDate(task.next_run) }}</div>
          </div>

          <v-divider class="my-3" />
          <div class="d-flex justify-end ga-2">
            <v-btn size="small" variant="tonal" color="success" prepend-icon="mdi-play" @click="handleRun(task.id)">执行</v-btn>
            <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-pencil" @click="openEdit(task)">编辑</v-btn>
            <v-btn size="small" variant="tonal" color="error" prepend-icon="mdi-delete-outline" @click="handleDelete(task.id, task.name)">删除</v-btn>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- 空状态 -->
    <v-card v-else-if="!isLoading" variant="outlined" rounded="xl" class="pa-8">
      <div class="text-center">
        <v-icon size="64" color="grey-lighten-1">mdi-clock-alert-outline</v-icon>
        <h3 class="text-h6 mt-3 mb-2">暂无定时任务</h3>
        <p class="text-caption text-medium-emphasis mb-4">创建定时任务以自动执行常规操作</p>
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openAdd">新建任务</v-btn>
      </div>
    </v-card>

    <!-- 新建/编辑对话框 -->
    <v-dialog v-model="showDialog" :max-width="form.task_type === 'workflow' ? 900 : 600" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon :icon="isEditing ? 'mdi-pencil' : 'mdi-plus'" class="mr-2" />
          {{ isEditing ? '编辑任务' : '新建任务' }}
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <!-- 基本信息 -->
          <v-text-field v-model="form.name" label="任务名称 *" density="compact" variant="outlined" />
          <v-select v-model="form.task_type" :items="taskTypeOptions" item-title="title" item-value="value"
            label="任务类型 *" density="compact" variant="outlined" @update:model-value="onTaskTypeChange" />

          <!-- 定时模式切换 -->
          <div class="d-flex align-center mb-2">
            <v-btn-toggle v-model="scheduleMode" density="compact" variant="outlined" divided mandatory>
              <v-btn value="simple" size="small">简易模式</v-btn>
              <v-btn value="advanced" size="small">Cron 表达式</v-btn>
            </v-btn-toggle>
          </div>

          <!-- 简易模式 -->
          <div v-if="scheduleMode === 'simple'" class="pa-3 rounded mb-3">
            <v-row density="compact">
              <v-col cols="6">
                <v-select v-model="simpleSchedule.type" :items="[
                  { title: '每天', value: 'daily' },
                  { title: '每周', value: 'weekly' },
                  { title: '每小时', value: 'hourly' },
                  { title: '间隔小时', value: 'interval' },
                ]" label="执行频率" density="compact" variant="outlined" />
              </v-col>
              <v-col v-if="simpleSchedule.type === 'daily' || simpleSchedule.type === 'weekly'" cols="3">
                <v-select v-model="simpleSchedule.hour" :items="hourOptions" label="时" density="compact" variant="outlined" />
              </v-col>
              <v-col v-if="simpleSchedule.type === 'daily' || simpleSchedule.type === 'weekly'" cols="3">
                <v-select v-model="simpleSchedule.minute" :items="minuteOptions" label="分" density="compact" variant="outlined" />
              </v-col>
              <v-col v-if="simpleSchedule.type === 'weekly'" cols="6">
                <v-select v-model="simpleSchedule.dayOfWeek" :items="dayOptions" label="周几" density="compact" variant="outlined" />
              </v-col>
              <v-col v-if="simpleSchedule.type === 'interval'" cols="6">
                <div class="text-caption mb-1">间隔 ({{ simpleSchedule.intervalHours }} 小时)</div>
                <v-slider v-model="simpleSchedule.intervalHours" :min="1" :max="23" :step="1" thumb-label
                  color="primary" track-color="grey-darken-1" />
              </v-col>
            </v-row>
            <div class="text-caption text-medium-emphasis mt-1">
              生成表达式: <code>{{ form.cron_expression }}</code>
            </div>
          </div>

          <!-- 高级 Cron -->
          <v-text-field v-else v-model="form.cron_expression" label="Cron 表达式 *" density="compact" variant="outlined"
            placeholder="0 */6 * * * (每6小时)" hint="分 时 日 月 周" persistent-hint />

          <v-checkbox v-model="form.enabled" label="启用" density="compact" hide-details class="mt-2" />

          <!-- ============ 任务参数 ============ -->
          <v-divider class="my-4" />
          <div class="text-subtitle-2 mb-3">任务参数设置</div>

          <!-- 封面生成器参数 -->
          <div v-if="form.task_type === 'cover'">
            <v-select v-model="taskParams.library_ids" :items="libraries" item-title="title" item-value="value"
              label="媒体库" density="compact" variant="outlined" multiple chips />
            <v-row density="compact">
              <v-col cols="6">
                <v-select v-model="taskParams.style_type" :items="styleOptionsCovers" item-title="title" item-value="value"
                  label="封面样式" density="compact" variant="outlined" />
              </v-col>
              <v-col cols="6">
                <v-select v-model="taskParams.sort_by" :items="[
                  { title: '随机', value: 'Random' },
                  { title: '添加日期', value: 'DateCreated' },
                  { title: '发行年份', value: 'ProductionYear' },
                  { title: '评分', value: 'CommunityRating' },
                ]" label="图片排序" density="compact" variant="outlined" />
              </v-col>
            </v-row>
            <v-textarea v-model="taskParams.title_config" label="标题映射配置" density="compact" variant="outlined" rows="2" auto-grow
              placeholder="媒体库名:中文标题:英文标题 (每行一个)" />

            <v-row density="compact">
              <v-col cols="6">
                <v-select v-model="taskParams.font_zh" :items="fonts" item-title="title" item-value="value"
                  label="中文字体" density="compact" variant="outlined" />
              </v-col>
              <v-col cols="6">
                <v-select v-model="taskParams.font_en" :items="fonts" item-title="title" item-value="value"
                  label="英文字体" density="compact" variant="outlined" />
              </v-col>
            </v-row>

            <v-row density="compact">
              <v-col cols="6">
                <div class="text-caption mb-1">中文缩放 ({{ taskParams.zh_font_size_ratio }}x)</div>
                <v-slider v-model="taskParams.zh_font_size_ratio" :min="0.1" :max="3" :step="0.1" thumb-label
                  color="primary" track-color="grey-darken-1" />
              </v-col>
              <v-col cols="6">
                <div class="text-caption mb-1">英文缩放 ({{ taskParams.en_font_size_ratio }}x)</div>
                <v-slider v-model="taskParams.en_font_size_ratio" :min="0.1" :max="3" :step="0.1" thumb-label
                  color="primary" track-color="grey-darken-1" />
              </v-col>
            </v-row>

            <v-row density="compact">
              <v-col cols="6">
                <div class="text-caption mb-1">背景模糊 ({{ taskParams.blur_size }})</div>
                <v-slider v-model="taskParams.blur_size" :min="0" :max="100" thumb-label
                  color="primary" track-color="grey-darken-1" />
              </v-col>
              <v-col cols="6">
                <div class="text-caption mb-1">主色占比 ({{ taskParams.color_ratio }})</div>
                <v-slider v-model="taskParams.color_ratio" :min="0" :max="1" :step="0.1" thumb-label
                  color="primary" track-color="grey-darken-1" />
              </v-col>
            </v-row>

            <v-select v-if="isAnimatedCoverStyle" v-model="taskParams.animation_format" :items="[
              { title: 'APNG (推荐)', value: 'png' },
              { title: 'GIF', value: 'gif' },
              { title: 'WebP', value: 'webp' },
            ]" label="动画格式" density="compact" variant="outlined" />

            <v-row density="compact">
              <v-col cols="4">
                <v-checkbox v-model="taskParams.is_blur" label="强制模糊" density="compact" hide-details />
              </v-col>
              <v-col cols="4">
                <v-checkbox v-model="taskParams.use_primary_first" label="优先主图" density="compact" hide-details />
              </v-col>
              <v-col cols="4">
                <v-checkbox v-model="taskParams.upload" label="自动上传" density="compact" hide-details />
              </v-col>
            </v-row>
          </div>

          <!-- 合集海报参数 -->
          <div v-else-if="form.task_type === 'collection_poster'">
            <v-textarea v-model="taskParams.collection_names_str" label="指定合集名称" density="compact" variant="outlined" rows="2" auto-grow
              placeholder="输入合集名称，用逗号分隔。留空则处理所有合集。" />

            <v-select v-model="taskParams.style_type" :items="styleOptionsCollections" item-title="title" item-value="value"
              label="海报样式" density="compact" variant="outlined" />

            <v-row density="compact">
              <v-col cols="6">
                <v-select v-model="taskParams.font_zh" :items="fonts" item-title="title" item-value="value"
                  label="中文字体" density="compact" variant="outlined" />
              </v-col>
              <v-col cols="6">
                <v-select v-model="taskParams.font_en" :items="fonts" item-title="title" item-value="value"
                  label="英文字体" density="compact" variant="outlined" />
              </v-col>
            </v-row>

            <v-row density="compact">
              <v-col cols="6">
                <div class="text-caption mb-1">中文缩放 ({{ taskParams.zh_font_size_ratio }}x)</div>
                <v-slider v-model="taskParams.zh_font_size_ratio" :min="0.1" :max="2" :step="0.1" thumb-label
                  color="primary" track-color="grey-darken-1" />
              </v-col>
              <v-col cols="6">
                <div class="text-caption mb-1">英文缩放 ({{ taskParams.en_font_size_ratio }}x)</div>
                <v-slider v-model="taskParams.en_font_size_ratio" :min="0.1" :max="2" :step="0.1" thumb-label
                  color="primary" track-color="grey-darken-1" />
              </v-col>
            </v-row>

            <v-row density="compact">
              <v-col cols="6">
                <v-text-field v-model.number="taskParams.offset_x" label="X 轴偏移" density="compact" variant="outlined" type="number" />
              </v-col>
              <v-col cols="6">
                <v-text-field v-model.number="taskParams.offset_y" label="Y 轴偏移" density="compact" variant="outlined" type="number" />
              </v-col>
            </v-row>

            <v-select v-model="taskParams.resolution_scale" :items="resolutionOptions" item-title="title" item-value="value"
              label="分辨率缩放" density="compact" variant="outlined" />

            <v-row density="compact">
              <v-col cols="6">
                <v-checkbox v-model="taskParams.show_zh" label="显示中文" density="compact" hide-details />
              </v-col>
              <v-col cols="6">
                <v-checkbox v-model="taskParams.show_en" label="显示英文" density="compact" hide-details />
              </v-col>
            </v-row>
          </div>

          <!-- Bangumi-Data 同步参数 -->
          <div v-else-if="form.task_type === 'bangumi_data_sync'">
            <v-alert type="info" variant="tonal" density="compact">
              此任务会自动从 CDN 下载 bangumi-data 数据，提取 TMDB-Bangumi ID 映射写入数据库。GitHub Token 已在系统设置中配置，无需额外参数。
            </v-alert>
          </div>

          <!-- Bangumi 映射同步到 Emby 参数 -->
          <div v-else-if="form.task_type === 'bangumi_sync'">
            <v-select v-model="taskParams.item_types" :items="[
              { title: '电影 + 剧集', value: 'Movie,Series' },
              { title: '仅电影', value: 'Movie' },
              { title: '仅剧集', value: 'Series' },
            ]" label="扫描类型" density="compact" variant="outlined" />

            <v-row density="compact">
              <v-col cols="6">
                <v-checkbox v-model="taskParams.write_to_genres" label="写入类型 (Genres)" density="compact" hide-details />
              </v-col>
              <v-col cols="6">
                <v-checkbox v-model="taskParams.write_to_tags" label="写入标签 (Tags)" density="compact" hide-details />
              </v-col>
            </v-row>
            <v-checkbox v-model="taskParams.is_merge_mode" label="合并模式 (保留现有标签)" density="compact" hide-details />

            <v-alert type="info" variant="tonal" density="compact" class="mt-3">
              将 Bangumi 标签同步到 Emby。需要先在「Bangumi 映射管理」中建立 TMDB-BGM 映射关系。
            </v-alert>
          </div>

          <!-- 备份参数 -->
          <div v-else-if="form.task_type === 'backup'">
            <v-select v-model="taskParams.mode" :items="[
              { title: '快照', value: 'snapshot' },
              { title: '导出', value: 'export' },
            ]" label="备份模式" density="compact" variant="outlined" />
            <v-checkbox v-model="taskParams.include_override" label="包含覆盖数据" density="compact" hide-details />
            <v-checkbox v-model="taskParams.include_collections" label="包含合集信息" density="compact" hide-details />
          </div>

          <!-- 预览图清理参数 -->
          <div v-else-if="form.task_type === 'preview_cleanup'">
            <v-text-field v-model.number="taskParams.max_age_hours" label="清理期限 (小时)" density="compact" variant="outlined"
              type="number" :min="1" hint="删除超过此时间的预览图" persistent-hint />
          </div>

          <!-- 扫描媒体库参数 -->
          <div v-else-if="form.task_type === 'scan_library'">
            <v-alert type="info" variant="tonal" density="compact">
              此任务会扫描磁盘上的元数据缓存目录，将所有媒体项目信息重新同步到数据库。无需额外参数。
            </v-alert>
          </div>

          <!-- 工作流参数 -->
          <div v-else-if="form.task_type === 'workflow'">
            <v-select v-model="taskParams.item_type" :items="[
              { title: '剧集 (TV)', value: 'tmdb-tv' },
              { title: '电影 (Movie)', value: 'tmdb-movies2' },
            ]" label="项目类型" density="compact" variant="outlined" />

            <div class="text-subtitle-2 mb-2 mt-3">工作流步骤</div>
            <div v-if="!taskParams.tasks?.length" class="text-caption text-medium-emphasis mb-2">暂无步骤，点击下方按钮添加</div>

            <v-card v-for="(step, idx) in taskParams.tasks" :key="idx" variant="outlined" rounded="lg" class="mb-3 pa-3">
              <div class="d-flex align-center ga-2 mb-2">
                <v-chip size="x-small" variant="flat" color="primary">{{ Number(idx) + 1 }}</v-chip>
                <v-select v-model="step.type" :items="workflowStepOptions" item-title="title" item-value="value"
                  density="compact" variant="outlined" hide-details class="flex-1"
                  @update:model-value="onWfStepTypeChange(step)" />
                <v-btn icon="mdi-delete-outline" variant="text" size="x-small" color="error" @click="taskParams.tasks.splice(idx, 1)" />
              </div>

              <!-- 步骤参数配置 -->
              <div v-if="step.params && Object.keys(step.params).length > 0" class="ml-4 pa-2 rounded-lg">
                <!-- Download Web Images -->
                <div v-if="step.type === 'download_web_images'">
                  <div class="text-caption text-medium-emphasis mb-1">来源:</div>
                  <div class="d-flex ga-2 mb-2">
                    <v-checkbox v-model="step.params.sources" value="tmdb" label="TMDb" density="compact" hide-details />
                    <v-checkbox v-model="step.params.sources" value="fanart" label="Fanart" density="compact" hide-details />
                  </div>
                  <div class="text-caption text-medium-emphasis mb-1">类型:</div>
                  <div class="d-flex flex-wrap ga-2 mb-2">
                    <v-checkbox v-model="step.params.image_types" value="poster" label="海报" density="compact" hide-details />
                    <v-checkbox v-model="step.params.image_types" value="fanart" label="背景" density="compact" hide-details />
                    <v-checkbox v-model="step.params.image_types" value="logo" label="Logo" density="compact" hide-details />
                    <v-checkbox v-model="step.params.image_types" value="clearart" label="艺术图" density="compact" hide-details />
                    <v-checkbox v-model="step.params.image_types" value="thumb" label="缩略图" density="compact" hide-details />
                    <v-checkbox v-model="step.params.image_types" value="banner" label="横幅" density="compact" hide-details />
                    <v-checkbox v-model="step.params.image_types" value="disc" label="光盘" density="compact" hide-details />
                  </div>
                  <v-row density="compact">
                    <v-col cols="4">
                      <v-select v-model="step.params.behavior" :items="[{title:'覆盖',value:'overwrite'},{title:'跳过',value:'skip'}]" label="模式" density="compact" variant="outlined" hide-details />
                    </v-col>
                    <v-col cols="4">
                      <v-select v-model="step.params.lang_priority" :items="[{title:'中文 (zh)',value:'zh'},{title:'英文 (en)',value:'en'},{title:'无偏好',value:''}]" label="优先语言" density="compact" variant="outlined" hide-details />
                    </v-col>
                  </v-row>
                </div>

                <!-- Emby Update Metadata -->
                <div v-if="step.type === 'emby_update_metadata'">
                  <div class="text-caption text-medium-emphasis mb-1">主信息字段:</div>
                  <v-select v-model="step.params.fields_to_update" :items="wfBaseFields" multiple chips density="compact" variant="outlined" hide-details class="mb-2" />
                  <v-checkbox v-model="step.params.update_children" label="更新子项 (季/集)" density="compact" hide-details />
                  <template v-if="step.params.update_children">
                    <div class="text-caption text-medium-emphasis mb-1 mt-2">子项字段:</div>
                    <v-select v-model="step.params.child_fields" :items="wfChildFields" multiple chips density="compact" variant="outlined" hide-details />
                  </template>
                </div>

                <!-- TMDB Update Metadata -->
                <div v-if="step.type === 'tmdb_update_metadata'">
                  <v-select v-model="step.params.lang" :items="wfLanguageOptions" label="语言" density="compact" variant="outlined" hide-details class="mb-2" />
                  <div class="text-caption text-medium-emphasis mb-1">更新字段:</div>
                  <v-select v-model="step.params.fields_to_update" :items="wfTmdbFields" multiple chips density="compact" variant="outlined" hide-details class="mb-2" />
                  <div class="d-flex ga-2">
                    <v-checkbox v-model="step.params.overwrite" label="覆盖现有" density="compact" hide-details />
                    <v-checkbox v-model="step.params.trigger_emby_refresh" label="刷新Emby" density="compact" hide-details />
                  </div>
                  <v-checkbox v-if="!isWfMovie" v-model="step.params.update_season_episodes" label="同时更新所有季/集" density="compact" hide-details />
                  <template v-if="step.params.update_season_episodes">
                    <div class="text-caption text-medium-emphasis mb-1 mt-2">季/集字段:</div>
                    <v-select v-model="step.params.child_fields" :items="wfTmdbChildFields" multiple chips density="compact" variant="outlined" hide-details />
                  </template>
                </div>

                <!-- Bangumi Update Metadata -->
                <div v-if="step.type === 'bangumi_update_metadata'">
                  <div class="text-caption text-medium-emphasis mb-1">更新字段:</div>
                  <v-select v-model="step.params.fields_to_update" :items="wfBangumiFields" multiple chips density="compact" variant="outlined" hide-details class="mb-2" />
                  <v-select v-model="step.params.mode" :items="[{title:'合并 (保留现有)',value:'merge'},{title:'覆盖 (完全替换)',value:'overwrite'}]" label="模式" density="compact" variant="outlined" hide-details class="mb-2" />
                  <div class="d-flex ga-2">
                    <v-checkbox v-model="step.params.use_whitelist" label="标签白名单" density="compact" hide-details />
                    <v-checkbox v-model="step.params.force_refresh" label="强制刷新缓存" density="compact" hide-details />
                  </div>
                  <v-checkbox v-model="step.params.auto_match" label="自动匹配缺失关联 (推荐)" density="compact" hide-details color="success" />
                </div>

                <!-- Lock Name -->
                <div v-if="step.type === 'lock_name'">
                  <div class="text-caption text-medium-emphasis">将当前名称写入 patches 文件，无需选择模式</div>
                </div>

                <!-- Delete Override Files -->
                <div v-if="step.type === 'delete_override_files'">
                  <v-select v-model="step.params.targets" :items="[
                    { title: '元数据 JSON', value: 'metadata' },
                    { title: '标签文件', value: 'tags' },
                    { title: '外部ID文件', value: 'external_ids' },
                    { title: '特别篇插入', value: 'episode_order' },
                    { title: '剧集组文件', value: 'episode_group' },
                  ]" multiple chips label="删除目标" density="compact" variant="outlined" hide-details />
                </div>

                <!-- AI Translate -->
                <div v-if="step.type === 'ai_translate'">
                  <div class="text-caption text-medium-emphasis mb-1">翻译内容选择:</div>
                  <div class="d-flex flex-wrap ga-2 mb-2">
                    <v-checkbox v-model="step.params.title" label="标题" density="compact" hide-details />
                    <v-checkbox v-model="step.params.overview" label="简介" density="compact" hide-details />
                    <template v-if="!isWfMovie">
                      <v-checkbox v-model="step.params.season_title" label="季标题" density="compact" hide-details />
                      <v-checkbox v-model="step.params.season_overview" label="季简介" density="compact" hide-details />
                      <v-checkbox v-model="step.params.episode_title" label="集标题" density="compact" hide-details />
                      <v-checkbox v-model="step.params.episode_overview" label="集简介" density="compact" hide-details />
                    </template>
                    <v-checkbox v-model="step.params.credits" label="演职员" density="compact" hide-details />
                  </div>
                  <div v-if="step.params.credits" class="pa-2 border rounded bg-surface mt-2">
                    <div class="text-caption text-success font-weight-bold mb-1">演职员翻译细节:</div>
                    <v-checkbox v-if="!isWfMovie" v-model="step.params.include_children_credits" label="包含所有季/集演职员" density="compact" hide-details />
                    <div class="d-flex flex-wrap ga-2">
                      <v-checkbox v-model="step.params.credits_options.cast_name" label="演员姓名" density="compact" hide-details />
                      <v-checkbox v-model="step.params.credits_options.cast_character" label="角色名" density="compact" hide-details />
                      <v-checkbox v-model="step.params.credits_options.crew_name" label="制作人姓名" density="compact" hide-details />
                      <v-checkbox v-model="step.params.credits_options.crew_job" label="职位" density="compact" hide-details />
                    </div>
                  </div>
                </div>
              </div>
            </v-card>

            <v-btn size="small" variant="tonal" prepend-icon="mdi-plus" @click="addWorkflowStep" class="mb-3">添加步骤</v-btn>

            <div class="text-caption mb-1">步骤间隔 ({{ taskParams.interval_seconds }} 秒)</div>
            <v-slider v-model="taskParams.interval_seconds" :min="0" :max="30" :step="1" thumb-label
              color="primary" track-color="grey-darken-1" />

            <v-alert type="info" variant="tonal" density="compact" class="mt-2">
              工作流会按顺序对匹配的项目依次执行所有步骤。适用于批量下载图片、更新元数据、同步到 Emby 等场景。
            </v-alert>
          </div>
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showDialog = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-content-save" @click="handleSave">{{ isEditing ? '保存' : '创建' }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

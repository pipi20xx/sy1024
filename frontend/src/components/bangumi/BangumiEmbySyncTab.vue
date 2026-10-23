<script setup lang="ts">
import { ref, reactive, nextTick, onMounted } from 'vue'
import { useNotification } from '@/composables'
import { getBangumiConfigApi } from '@/api/bangumi'
import { api } from '@/api/client'

const { notify } = useNotification()

const DEFAULT_ALLOWED_TAGS = `异世界
后宫
轮回
轻小说改
游戏改
GAL改
漫画改
京阿尼
Key
芳文社
MAPPA
P.A.WORKS
原创
MADHouse
宫崎骏
吉卜力
动画工房
A-1 Pictures
Production I.G
Wit Studio
ufotable
BONES
SUNRISE
TRIGGER
CloverWorks
SHAFT
Studio Deen
日常
搞笑
战斗
催泪
致郁
治愈
校园
恋爱
奇幻
科幻
悬疑
推理
恐怖
泡面番
穿越
百合
耽美
热血
运动
音乐
美食
偶像
机战
魔法少女
历史
战争
空气系
萌系
剧情系
反乌托邦
赛博朋克`

const syncConfig = reactive({
  item_types: ['Movie', 'Series'] as string[],
  write_to_genres: true,
  write_to_tags: true,
  is_merge_mode: true,
  is_preview: true,
  allowed_tags_str: DEFAULT_ALLOWED_TAGS,
})

// 从后端加载配置
onMounted(async () => {
  try {
    const data = await getBangumiConfigApi()
    if (data.sync_config) {
      if (Array.isArray(data.sync_config.item_types)) syncConfig.item_types = data.sync_config.item_types
      if (data.sync_config.write_to_genres !== undefined) syncConfig.write_to_genres = data.sync_config.write_to_genres
      if (data.sync_config.write_to_tags !== undefined) syncConfig.write_to_tags = data.sync_config.write_to_tags
      if (data.sync_config.is_merge_mode !== undefined) syncConfig.is_merge_mode = data.sync_config.is_merge_mode
      if (data.sync_config.is_preview !== undefined) syncConfig.is_preview = data.sync_config.is_preview
      if (Array.isArray(data.sync_config.allowed_tags) && data.sync_config.allowed_tags.length > 0) {
        syncConfig.allowed_tags_str = data.sync_config.allowed_tags.join('\n')
      }
    }
  } catch (e) {
    console.error('Failed to load bangumi sync config:', e)
  }
})

const isSavingConfig = ref(false)

async function handleSaveConfig() {
  isSavingConfig.value = true
  try {
    const tagsList = syncConfig.allowed_tags_str
      .split('\n')
      .map((t: string) => t.trim())
      .filter((t: string) => t.length > 0)
    await api.post('/api/bangumi-sync/config', { allowed_tags: tagsList })
    notify('保存成功', '标签白名单已保存', 'success')
  } catch (e: any) {
    notify('保存失败', e.message || '未知错误', 'error')
  } finally {
    isSavingConfig.value = false
  }
}

const embySyncing = ref(false)
const embySyncProgress = ref(0)
const embySyncLogs = ref<string[]>([])
const embySyncLogContainer = ref<HTMLElement | null>(null)

async function startEmbySync() {
  embySyncing.value = true
  embySyncProgress.value = 0
  embySyncLogs.value = []

  const tagsList = syncConfig.allowed_tags_str
    .split('\n')
    .map((t: string) => t.trim())
    .filter((t: string) => t.length > 0)

  const payload = {
    item_types: syncConfig.item_types.join(','),
    write_to_genres: syncConfig.write_to_genres,
    write_to_tags: syncConfig.write_to_tags,
    is_merge_mode: syncConfig.is_merge_mode,
    is_preview: syncConfig.is_preview,
    allowed_tags_filter: tagsList,
  }

  try {
    const accessToken = localStorage.getItem('access_token')
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`

    const response = await fetch('/api/bangumi-sync/run', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    })
    if (!response.ok) throw new Error(response.statusText)

    const reader = response.body?.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    if (!reader) throw new Error('Cannot read stream')

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.substring(6))
            if (data.type === 'log') embySyncLogs.value.push(data.message)
            else if (data.type === 'progress') embySyncProgress.value = data.message
            else if (data.type === 'finished') {
              embySyncLogs.value.push(data.message)
              embySyncing.value = false
              notify('同步任务完成', '', 'success')
            } else if (data.type === 'error') {
              embySyncLogs.value.push(`[错误] ${data.message}`)
              notify('同步出错', data.message, 'error')
            }
            nextTick(() => {
              if (embySyncLogContainer.value)
                embySyncLogContainer.value.scrollTop = embySyncLogContainer.value.scrollHeight
            })
          } catch (e) { /* ignore parse errors */ }
        }
      }
    }
  } catch (e: any) {
    notify('请求失败', e.message, 'error')
    embySyncing.value = false
  }
}

</script>

<template>
  <v-row>
    <!-- 同步配置 -->
    <v-col cols="12" md="4">
      <v-card variant="outlined" rounded="xl" class="pa-4" height="100%">
        <div class="text-subtitle-2 font-weight-bold mb-3">同步配置</div>

        <div class="mb-3">
          <div class="text-body-2 mb-1">媒体类型</div>
          <v-checkbox v-model="syncConfig.item_types" value="Movie" label="电影 (Movie)" density="compact" hide-details />
          <v-checkbox v-model="syncConfig.item_types" value="Series" label="剧集 (Series)" density="compact" hide-details />
        </div>

        <div class="mb-3">
          <div class="text-body-2 mb-1">写入字段</div>
          <v-checkbox v-model="syncConfig.write_to_genres" label="写入流派 (Genres)" density="compact" hide-details />
          <v-checkbox v-model="syncConfig.write_to_tags" label="写入标签 (Tags)" density="compact" hide-details />
        </div>

        <div class="mb-3">
          <div class="text-body-2 mb-1">合并模式</div>
          <v-switch
            v-model="syncConfig.is_merge_mode"
            :label="syncConfig.is_merge_mode ? '合并 (保留现有)' : '覆盖 (替换现有)'"
            density="compact"
            hide-details
            color="primary"
          />
        </div>

        <div class="mb-3">
          <v-textarea
            v-model="syncConfig.allowed_tags_str"
            label="标签白名单"
            variant="outlined"
            placeholder="每行一个标签"
            :rows="5"
            density="compact"
          />
        </div>

        <div class="d-flex justify-end mt-3">
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-content-save" :loading="isSavingConfig" @click="handleSaveConfig">
            保存配置
          </v-btn>
        </div>
      </v-card>
    </v-col>

    <!-- 执行同步 -->
    <v-col cols="12" md="8">
      <v-card variant="outlined" rounded="xl" class="pa-4 d-flex flex-column" height="100%">
        <div class="text-subtitle-2 font-weight-bold mb-3">执行同步</div>

        <div class="d-flex flex-wrap align-center ga-3 mb-3">
          <v-switch
            v-model="syncConfig.is_preview"
            :label="syncConfig.is_preview ? '预览模式 (不写入)' : '写入模式 (修改数据)'"
            density="compact"
            hide-details
            :color="syncConfig.is_preview ? 'info' : 'warning'"
          />
          <v-btn
            :color="syncConfig.is_preview ? 'info' : 'warning'"
            variant="tonal"
            prepend-icon="mdi-play"
            :loading="embySyncing"
            :disabled="embySyncing"
            @click="startEmbySync"
          >
            {{ embySyncing ? '正在执行...' : '开始执行' }}
          </v-btn>
        </div>

        <v-progress-linear
          v-if="embySyncing || embySyncProgress > 0"
          :model-value="embySyncProgress"
          color="primary"
          height="6"
          rounded
          class="mb-3"
          :indeterminate="embySyncing && embySyncProgress === 0"
        />

        <div
          ref="embySyncLogContainer"
          class="pa-3 log-window flex-1 loading-state"
        >
        <div
          v-for="(log, idx) in embySyncLogs"
          :key="idx"
          class="log-line"
          :class="{
            'log-error': log.includes('错误') || log.includes('失败'),
          }"
        >
          {{ log }}
        </div>
        </div>
      </v-card>
    </v-col>
  </v-row>
</template>

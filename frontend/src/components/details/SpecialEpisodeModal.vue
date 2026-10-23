<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { getEpisodeOrder, updateEpisodeOrder } from '@/api/details'
import { useNotification, useConfirm } from '@/composables'
import JsonEditorDialog from '@/components/common/JsonEditorDialog.vue'
import type { EpisodeOrder, EpisodeOrderEntry } from '@/types'

const props = defineProps<{
  modelValue: boolean
  seriesId: string
  seriesName: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  refresh: []
}>()

const { notify } = useNotification()
const { confirm } = useConfirm()

const loading = ref(false)
const currentData = ref<EpisodeOrder>({ description: '', seasons: [] })

// 原始 JSON 编辑弹框状态
const showJsonEditor = ref(false)

// 添加规则表单
const newEntry = ref({
  originalEp: 1,
  targetSeason: 1,
  targetEp: 1,
})

// 对话框打开时加载数据
watch(() => props.modelValue, (val) => {
  if (val) loadData()
})

async function loadData() {
  loading.value = true
  try {
    const data = await getEpisodeOrder(props.seriesId)
    if (!data.seasons) data.seasons = []
    currentData.value = data
    // 确保 season 0 存在
    if (!data.seasons.find(s => s.season_number === 0)) {
      currentData.value.seasons.push({ season_number: 0, episodes: [] })
    }
  } catch (e: any) {
    if (e.response?.status === 404) {
      currentData.value = { description: '', seasons: [{ season_number: 0, episodes: [] }] }
    } else {
      notify('加载失败', e.message || '未知错误', 'error')
    }
  } finally {
    loading.value = false
  }
}

// 当前规则列表
const entries = computed(() => {
  const season0 = currentData.value.seasons.find(s => s.season_number === 0)
  return season0 ? season0.episodes : []
})

function addEntry() {
  const season0 = currentData.value.seasons.find(s => s.season_number === 0)
  if (!season0) return

  season0.episodes.push({
    episode_number: newEntry.value.originalEp,
    sort_season_number: newEntry.value.targetSeason,
    sort_episode_number: newEntry.value.targetEp,
  })

  season0.episodes.sort((a, b) => a.episode_number - b.episode_number)
  notify('已添加', '', 'success')
  // 自动递增集号，方便连续添加
  newEntry.value.originalEp++
}

async function removeEntry(index: number) {
  const ok = await confirm({
    title: '移除规则',
    content: `确认移除 S0 E${entries.value[index].episode_number} 的插入规则？`,
    confirmColor: 'error',
  })
  if (!ok) return
  const season0 = currentData.value.seasons.find(s => s.season_number === 0)
  if (season0) {
    season0.episodes.splice(index, 1)
  }
}

async function handleSave() {
  loading.value = true
  try {
    await updateEpisodeOrder(props.seriesId, currentData.value)
    notify('保存成功', '', 'success')
    emit('refresh')
    emit('update:modelValue', false)
  } catch (e: any) {
    notify('保存失败', e.message, 'error')
  } finally {
    loading.value = false
  }
}

function applyJsonEdit(parsed: any) {
  if (parsed.seasons !== undefined && !Array.isArray(parsed.seasons)) {
    notify('JSON 格式错误', 'seasons 字段必须是数组', 'error')
    return
  }
  if (!parsed.seasons) parsed.seasons = []
  for (const season of parsed.seasons) {
    if (!season || typeof season !== 'object') {
      notify('JSON 格式错误', 'seasons 内的每一项必须是对象', 'error')
      return
    }
    if (!Array.isArray(season.episodes)) season.episodes = []
  }
  // 确保 season 0 存在，与 loadData 行为一致，表单才能继续添加规则
  if (!parsed.seasons.find((s: any) => s.season_number === 0)) {
    parsed.seasons.push({ season_number: 0, episodes: [] })
  }
  currentData.value = parsed
  showJsonEditor.value = false
  notify('JSON 已应用', '需点击底部保存以生效', 'success')
}

function handleClose() {
  emit('update:modelValue', false)
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    max-width="800"
    scrollable
  >
    <v-card>
      <!-- 标题栏 -->
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-playlist-play" class="mr-2" />
        特别篇插入: {{ seriesName }}
        <v-spacer />
        <v-tooltip location="top">
          <template #activator="{ props }">
            <v-btn v-bind="props" icon="mdi-code-block-braces" variant="text" size="small" :disabled="loading" @click="showJsonEditor = true" />
          </template>
          编辑原始 JSON
        </v-tooltip>
        <v-btn icon="mdi-close" variant="text" size="small" @click="handleClose" />
      </v-card-title>
      <v-divider />

      <v-card-text class="pa-0">
        <v-progress-linear v-if="loading" indeterminate color="primary" />

        <div class="pa-4">
          <!-- 描述 -->
          <v-text-field
            v-model="currentData.description"
            label="描述 (Description)"
            placeholder="例如：按播出顺序排列"
            density="compact"
            variant="outlined"
            hide-details
            class="mb-4"
          />

          <!-- 添加规则卡片 -->
          <v-card variant="outlined" rounded="xl" class="pa-4 mb-4">
            <div class="text-subtitle-2 font-weight-bold mb-3">
              <v-icon start size="small">mdi-plus-circle-outline</v-icon>
              添加新规则
            </div>
            <v-row align="center" density="compact">
              <v-col cols="12" sm="3">
                <v-text-field
                  v-model.number="newEntry.originalEp"
                  type="number"
                  label="S0 集号"
                  density="compact"
                  variant="outlined"
                  hide-details
                  min="1"
                  prefix="S0 E"
                />
              </v-col>
              <v-col cols="auto" class="d-flex align-center justify-center text-medium-emphasis">
                <v-icon>mdi-arrow-right</v-icon>
              </v-col>
              <v-col cols="5" sm="2">
                <v-text-field
                  v-model.number="newEntry.targetSeason"
                  type="number"
                  label="目标季"
                  density="compact"
                  variant="outlined"
                  hide-details
                  min="1"
                  prefix="S"
                />
              </v-col>
              <v-col cols="5" sm="2">
                <v-text-field
                  v-model.number="newEntry.targetEp"
                  type="number"
                  label="目标集"
                  density="compact"
                  variant="outlined"
                  hide-details
                  min="1"
                  prefix="E"
                />
              </v-col>
              <v-col cols="2" sm="auto" class="d-flex align-center justify-center text-caption text-medium-emphasis">
                之前
              </v-col>
              <v-col cols="12" sm="auto" class="d-flex justify-end">
                <v-btn size="small" color="primary" variant="tonal" @click="addEntry" prepend-icon="mdi-plus">添加</v-btn>
              </v-col>
            </v-row>
          </v-card>

          <!-- 规则列表 -->
          <div class="d-flex align-center mb-2">
            <div class="text-subtitle-2 font-weight-bold">
              <v-icon start size="small">mdi-format-list-numbered</v-icon>
              已有规则列表
            </div>
            <v-chip size="x-small" variant="tonal" class="ml-2">{{ entries.length }}</v-chip>
          </div>

          <template v-if="entries.length > 0">
            <div class="d-flex flex-column ga-2">
              <v-card
                v-for="(entry, index) in entries"
                :key="index"
                variant="outlined"
                rounded="xl"
                class="pa-3"
              >
                <div class="d-flex align-center">
                  <div class="d-flex align-center flex-grow-1">
                    <v-chip size="small" variant="tonal" color="success" label class="mr-2">
                      S0 E{{ entry.episode_number }}
                    </v-chip>
                    <v-icon size="small" class="mx-2 text-medium-emphasis">mdi-arrow-right</v-icon>
                    <v-chip size="small" variant="tonal" color="info" label>
                      在 S{{ entry.sort_season_number }} E{{ entry.sort_episode_number }} 之前
                    </v-chip>
                  </div>
                  <v-btn size="x-small" variant="tonal" color="error" prepend-icon="mdi-delete-outline" @click="removeEntry(index)">移除</v-btn>
                </div>
              </v-card>
            </div>
          </template>
          <template v-else>
<v-card variant="outlined" rounded="xl" class="pa-8 text-center">
            <v-icon size="48" color="grey-lighten-1">mdi-playlist-remove</v-icon>
            <div class="mt-2 text-body-2 text-medium-emphasis">暂无规则</div>
            <div class="text-caption text-medium-emphasis">使用上方表单添加特别篇插入规则</div>
</v-card>
          </template>
        </div>
      </v-card-text>

      <v-divider />
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="handleClose">取消</v-btn>
        <v-btn color="primary" variant="tonal" @click="handleSave" :loading="loading" prepend-icon="mdi-content-save">保存更改</v-btn>
      </v-card-actions>
    </v-card>

    <!-- 原始 JSON 编辑对话框 -->
    <JsonEditorDialog
      v-model="showJsonEditor"
      :initial-data="currentData"
      confirm-text="确定"
      hint="点击「确定」后应用到表单，需再点击底部「保存更改」才会写入文件"
      @confirm="applyJsonEdit"
    />
  </v-dialog>
</template>

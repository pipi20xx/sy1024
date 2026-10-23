<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { getEpisodeGroup, updateEpisodeGroup } from '@/api/details'
import { useNotification, useConfirm } from '@/composables'
import JsonEditorDialog from '@/components/common/JsonEditorDialog.vue'
import type { EpisodeGroup, EpisodeGroupGroup, EpisodeGroupEpisode } from '@/types'

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
const currentData = ref<EpisodeGroup>({ description: '', groups: [] })

// 元数据编辑弹框状态
const showEditMetadata = ref(false)
const editingGroup = ref<EpisodeGroupGroup | null>(null)
const metadataForm = ref({ overview: '', airDate: '' })

// 原始 JSON 编辑弹框状态
const showJsonEditor = ref(false)

// 添加分组表单
const newGroupForm = ref({
  name: '',
  overview: '',
  airDate: '',
  localSeason: 1,
  localStartEp: 1,
  tmdbSeason: 1,
  tmdbStartEp: 1,
  numEpisodes: 12,
})

// 对话框打开时加载数据
watch(() => props.modelValue, (val) => {
  if (val) loadData()
})

async function loadData() {
  loading.value = true
  try {
    const data = await getEpisodeGroup(props.seriesId)
    currentData.value = data || { description: '', groups: [] }
    if (!currentData.value.groups) currentData.value.groups = []
    resetAddForm(true)
  } catch (e: any) {
    if (e.response?.status === 404) {
      currentData.value = { description: '', groups: [] }
      resetAddForm()
    } else {
      notify('加载失败', e.message || '未知错误', 'error')
    }
  } finally {
    loading.value = false
  }
}

const sortedGroups = computed(() => {
  return [...currentData.value.groups].sort((a, b) => a.order - b.order)
})

function resetAddForm(autoIncrement = false) {
  const defaultNum = newGroupForm.value.numEpisodes

  if (autoIncrement && currentData.value.groups.length > 0) {
    const lastGroup = [...currentData.value.groups].sort((a, b) => a.order - b.order).pop()
    if (lastGroup && lastGroup.episodes && lastGroup.episodes.length > 0) {
      const sortedEps = [...lastGroup.episodes].sort((a, b) => a.order - b.order)
      const lastEp = sortedEps[sortedEps.length - 1]

      newGroupForm.value = {
        name: '',
        overview: '',
        airDate: '',
        localSeason: lastGroup.order + 1,
        localStartEp: 1,
        tmdbSeason: lastEp.season_number,
        tmdbStartEp: lastEp.episode_number + 1,
        numEpisodes: defaultNum,
      }
      return
    }
  }

  newGroupForm.value = {
    name: '',
    overview: '',
    airDate: '',
    localSeason: 1,
    localStartEp: 1,
    tmdbSeason: 1,
    tmdbStartEp: 1,
    numEpisodes: 12,
  }
}

function addGroup() {
  const form = newGroupForm.value

  let existingGroup = currentData.value.groups.find(g => g.order === form.localSeason)

  const episodesToAdd: EpisodeGroupEpisode[] = []
  for (let i = 0; i < form.numEpisodes; i++) {
    episodesToAdd.push({
      episode_number: form.tmdbStartEp + i,
      season_number: form.tmdbSeason,
      order: (form.localStartEp - 1) + i,
    })
  }

  if (existingGroup) {
    // 更新已有分组
    existingGroup.name = form.name || (form.localSeason === 0 ? '特别篇' : `第 ${form.localSeason} 季`)
    if (form.overview) existingGroup.overview = form.overview
    if (form.airDate) existingGroup.air_date = form.airDate

    // 合并剧集
    const existingKeys = new Set(existingGroup.episodes.map(e => `${e.season_number}-${e.episode_number}-${e.order}`))
    episodesToAdd.forEach(ep => {
      const key = `${ep.season_number}-${ep.episode_number}-${ep.order}`
      if (!existingKeys.has(key)) {
        existingGroup.episodes.push(ep)
        existingKeys.add(key)
      }
    })
    existingGroup.episodes.sort((a, b) => a.order - b.order)
  } else {
    // 创建新分组
    const newGroup: EpisodeGroupGroup = {
      name: form.name || (form.localSeason === 0 ? '特别篇' : `第 ${form.localSeason} 季`),
      order: form.localSeason,
      overview: form.overview || undefined,
      episodes: episodesToAdd,
    }
    if (form.airDate) newGroup.air_date = form.airDate
    currentData.value.groups.push(newGroup)
  }

  notify('已添加/更新分组', '', 'success')
  resetAddForm(true)
}

function openMetadataEditor(group: EpisodeGroupGroup) {
  editingGroup.value = group
  metadataForm.value.overview = group.overview || ''
  metadataForm.value.airDate = group.air_date || ''
  showEditMetadata.value = true
}

function saveMetadataEdit() {
  if (editingGroup.value) {
    if (metadataForm.value.overview) {
      editingGroup.value.overview = metadataForm.value.overview
    } else {
      delete editingGroup.value.overview
    }

    if (metadataForm.value.airDate) {
      editingGroup.value.air_date = metadataForm.value.airDate
    } else {
      delete editingGroup.value.air_date
    }
    notify('元数据已更新', '需点击底部保存以生效', 'success')
    showEditMetadata.value = false
  }
}

function applyJsonEdit(parsed: any) {
  if (parsed.groups !== undefined && !Array.isArray(parsed.groups)) {
    notify('JSON 格式错误', 'groups 字段必须是数组', 'error')
    return
  }
  if (!parsed.groups) parsed.groups = []
  for (const group of parsed.groups) {
    if (!group || typeof group !== 'object') {
      notify('JSON 格式错误', 'groups 内的每一项必须是对象', 'error')
      return
    }
    if (!Array.isArray(group.episodes)) group.episodes = []
  }
  currentData.value = parsed
  showJsonEditor.value = false
  notify('JSON 已应用', '需点击底部保存以生效', 'success')
}

async function removeGroup(index: number) {
  const groupToRemove = sortedGroups.value[index]
  const ok = await confirm({
    title: '移除分组',
    content: `确认移除「${groupToRemove.name}」？该分组内 ${groupToRemove.episodes.length} 集数据将被删除。`,
    confirmColor: 'error',
  })
  if (!ok) return
  const realIndex = currentData.value.groups.indexOf(groupToRemove)
  if (realIndex > -1) {
    currentData.value.groups.splice(realIndex, 1)
  }
}

// 计算分组的集数摘要
function getGroupSummary(group: EpisodeGroupGroup) {
  const epCount = group.episodes.length
  if (epCount === 0) return '无剧集'

  const sortedEps = [...group.episodes].sort((a, b) => a.order - b.order)

  const ranges: string[] = []
  if (sortedEps.length > 0) {
    let startS = sortedEps[0].season_number
    let startE = sortedEps[0].episode_number
    let endS = startS
    let endE = startE

    for (let i = 1; i < sortedEps.length; i++) {
      const ep = sortedEps[i]
      const prev = sortedEps[i - 1]
      if (ep.season_number === prev.season_number && ep.episode_number === prev.episode_number + 1) {
        endE = ep.episode_number
      } else {
        ranges.push(formatRange(startS, startE, endS, endE))
        startS = ep.season_number
        startE = ep.episode_number
        endS = startS
        endE = startE
      }
    }
    ranges.push(formatRange(startS, startE, endS, endE))
  }

  return `${epCount} 集 (TMDB: ${ranges.join(', ')})`
}

function formatRange(s1: number, e1: number, s2: number, e2: number) {
  if (s1 === s2 && e1 === e2) return `S${s1}E${e1}`
  return `S${s1}E${e1}-S${s2}E${e2}`
}

async function handleSave() {
  loading.value = true
  try {
    await updateEpisodeGroup(props.seriesId, currentData.value)
    notify('保存成功', '', 'success')
    emit('refresh')
    emit('update:modelValue', false)
  } catch (e: any) {
    notify('保存失败', e.message, 'error')
  } finally {
    loading.value = false
  }
}

function handleClose() {
  emit('update:modelValue', false)
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    max-width="1000"
    scrollable
  >
    <v-card>
      <!-- 标题栏 -->
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-group" class="mr-2" />
        编辑剧集组: {{ seriesName }}
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
          <!-- 全局描述 -->
          <v-text-field
            v-model="currentData.description"
            label="全局描述 (Description)"
            placeholder="例如：DVD 排序"
            density="compact"
            variant="outlined"
            hide-details
            class="mb-4"
          />

          <!-- 添加/更新分组 -->
          <v-card variant="outlined" rounded="xl" class="pa-4 mb-4">
            <div class="text-subtitle-2 font-weight-bold mb-3">
              <v-icon start size="small">mdi-plus-circle-outline</v-icon>
              添加/更新分组
            </div>

            <v-row density="compact">
              <v-col cols="12" sm="6" md="4">
                <v-text-field
                  v-model="newGroupForm.name"
                  label="季名称"
                  placeholder="默认: 第 X 季"
                  density="compact"
                  variant="outlined"
                  hide-details
                />
              </v-col>
              <v-col cols="6" sm="3" md="4">
                <v-text-field
                  v-model="newGroupForm.airDate"
                  label="首播日期"
                  placeholder="YYYY-MM-DD"
                  density="compact"
                  variant="outlined"
                  hide-details
                />
              </v-col>
              <v-col cols="6" sm="3" md="4">
                <v-text-field
                  v-model="newGroupForm.overview"
                  label="简介"
                  placeholder="可选"
                  density="compact"
                  variant="outlined"
                  hide-details
                />
              </v-col>

              <v-col cols="6" sm="3" md="3">
                <v-text-field
                  v-model.number="newGroupForm.localSeason"
                  type="number"
                  label="本地季号"
                  density="compact"
                  variant="outlined"
                  hide-details
                  min="0"
                />
              </v-col>
              <v-col cols="6" sm="3" md="3">
                <v-text-field
                  v-model.number="newGroupForm.localStartEp"
                  type="number"
                  label="本地起始集号"
                  density="compact"
                  variant="outlined"
                  hide-details
                  min="1"
                />
              </v-col>
              <v-col cols="6" sm="3" md="3">
                <v-text-field
                  v-model.number="newGroupForm.tmdbSeason"
                  type="number"
                  label="TMDB 季号"
                  density="compact"
                  variant="outlined"
                  hide-details
                  min="0"
                />
              </v-col>
              <v-col cols="6" sm="3" md="3">
                <v-text-field
                  v-model.number="newGroupForm.tmdbStartEp"
                  type="number"
                  label="TMDB 起始集号"
                  density="compact"
                  variant="outlined"
                  hide-details
                  min="1"
                />
              </v-col>
            </v-row>

            <div class="d-flex align-center justify-end mt-3 ga-3">
              <span class="text-caption text-medium-emphasis">连续添加集数:</span>
              <v-text-field
                v-model.number="newGroupForm.numEpisodes"
                type="number"
                density="compact"
                variant="outlined"
                hide-details
                min="1"
                class="mw-80px"
              />
              <v-btn size="small" color="primary" variant="tonal" @click="addGroup" prepend-icon="mdi-plus">添加/更新</v-btn>
            </div>
          </v-card>

          <!-- 分组列表 -->
          <div class="d-flex align-center mb-2">
            <div class="text-subtitle-2 font-weight-bold">
              <v-icon start size="small">mdi-format-list-group</v-icon>
              已有分组列表
            </div>
            <v-chip size="x-small" variant="tonal" class="ml-2">{{ sortedGroups.length }}</v-chip>
          </div>

          <template v-if="sortedGroups.length > 0">
            <div class="d-flex flex-column ga-2">
              <v-card
                v-for="(group, index) in sortedGroups"
                :key="index"
                variant="outlined"
                rounded="xl"
                class="pa-3"
              >
                <div class="d-flex align-start">
                  <div class="flex-grow-1">
                    <div class="d-flex align-center mb-1">
                      <span class="text-body-1 font-weight-bold">{{ group.name }}</span>
                      <v-chip size="x-small" variant="tonal" label class="ml-2">
                        本地第 {{ group.order }} 季
                      </v-chip>
                    </div>
                    <div class="text-body-2 text-medium-emphasis">
                      {{ getGroupSummary(group) }}
                    </div>
                    <div v-if="group.overview" class="text-caption text-medium-emphasis mt-1">
                      简介: {{ group.overview }}
                    </div>
                    <div v-if="group.air_date" class="text-caption text-medium-emphasis">
                      首播: {{ group.air_date }}
                    </div>
                  </div>
                  <div class="d-flex ga-1 ml-2">
                    <v-btn size="x-small" variant="tonal" color="primary" prepend-icon="mdi-pencil" @click="openMetadataEditor(group)">编辑</v-btn>
                    <v-btn size="x-small" variant="tonal" color="error" prepend-icon="mdi-delete-outline" @click="removeGroup(index)">删除</v-btn>
                  </div>
                </div>
              </v-card>
            </div>
          </template>
          <template v-else>
<v-card variant="outlined" rounded="xl" class="pa-8 text-center">
            <v-icon size="48" color="grey-lighten-1">mdi-group</v-icon>
            <div class="mt-2 text-body-2 text-medium-emphasis">暂无分组</div>
            <div class="text-caption text-medium-emphasis">使用上方表单添加剧集分组</div>
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

    <!-- 元数据编辑对话框 -->
    <v-dialog v-model="showEditMetadata" max-width="500">
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-pencil" class="mr-2" />
          编辑分组元数据
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showEditMetadata = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-textarea
            v-model="metadataForm.overview"
            label="季简介"
            density="compact"
            variant="outlined"
            rows="3"
            auto-grow
            class="mb-3"
          />
          <v-text-field
            v-model="metadataForm.airDate"
            label="季首播日期"
            placeholder="YYYY-MM-DD"
            density="compact"
            variant="outlined"
            hide-details
          />
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showEditMetadata = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-check" @click="saveMetadataEdit">确定</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

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

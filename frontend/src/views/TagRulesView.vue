<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchTagRules, addTagRule, updateTagRule, deleteTagRule } from '@/api/tagRules'
defineOptions({ name: 'TagRulesView' })
import { useNotification, useConfirm } from '@/composables'
import { countries, genres, getCountryName, getGenreName } from '@/constants/tagManagement'
import type { TagRule } from '@/types'
import explanationHtmlRaw from '@/assets/tag_rules_explanation.html?raw'

const { notify } = useNotification()
const { confirm } = useConfirm()

const rules = ref<TagRule[]>([])
const isLoading = ref(false)
const showDialog = ref(false)
const showExplanation = ref(false)
const explanationHtml = ref<string>(explanationHtmlRaw)
const isEditing = ref(false)
const editingId = ref<string | undefined>()

const defaultForm = (): Omit<TagRule, 'id'> => ({
  name: '',
  tag: '',
  countries: [],
  genres: [],
  media_type: 'all',
  year: '',
  strict_match: false,
  negative_match: false,
})

const form = ref(defaultForm())

const mediaTypeOptions = [
  { title: '全部', value: 'all' },
  { title: '电影', value: 'movie' },
  { title: '剧集', value: 'tv' },
]

onMounted(() => loadRules())

async function loadRules() {
  isLoading.value = true
  try { rules.value = await fetchTagRules() }
  catch (e: any) { notify('加载失败', e.message, 'error') }
  finally { isLoading.value = false }
}

function openAdd() {
  isEditing.value = false
  editingId.value = undefined
  form.value = defaultForm()
  showDialog.value = true
}

function openEdit(rule: TagRule) {
  isEditing.value = true
  editingId.value = rule.id
  form.value = {
    name: rule.name,
    tag: rule.tag,
    countries: [...(rule.countries || [])],
    genres: [...(rule.genres || [])],
    media_type: rule.media_type,
    year: Array.isArray(rule.year) ? rule.year.join(',') : rule.year,
    strict_match: rule.strict_match,
    negative_match: rule.negative_match,
  }
  showDialog.value = true
}

async function handleSave() {
  if (!form.value.name || !form.value.tag) {
    notify('提示', '规则名称和标签不能为空', 'warning')
    return
  }
  try {
    const submitData = { ...form.value }
    // Parse year
    const yearInput = String(submitData.year).trim()
    if (yearInput) {
      if (yearInput.includes('-')) {
        submitData.year = yearInput
      } else if (yearInput.includes(',')) {
        submitData.year = yearInput.split(',').map(y => parseInt(y.trim())).filter(y => !isNaN(y))
      } else {
        const singleYear = parseInt(yearInput)
        submitData.year = !isNaN(singleYear) ? singleYear : ''
      }
    } else {
      submitData.year = ''
    }
    if (isEditing.value && editingId.value) {
      await updateTagRule(editingId.value, { ...submitData, id: editingId.value })
      notify('更新成功', '', 'success')
    } else {
      await addTagRule(submitData)
      notify('添加成功', '', 'success')
    }
    showDialog.value = false
    await loadRules()
  } catch (e: any) {
    notify('保存失败', e.message, 'error')
  }
}

async function handleDelete(id: string, name: string) {
  const ok = await confirm({
    title: '删除规则',
    content: `确认删除规则「${name}」？`,
    confirmColor: 'error',
  })
  if (!ok) return
  try {
    await deleteTagRule(id)
    notify('已删除', '', 'success')
    await loadRules()
  } catch (e: any) {
    notify('删除失败', e.message, 'error')
  }
}

function toggleCountry(code: string) {
  const idx = form.value.countries?.indexOf(code)
  if (idx === undefined || idx === -1) {
    if (!form.value.countries) form.value.countries = []
    form.value.countries.push(code)
  } else {
    form.value.countries.splice(idx, 1)
  }
}

function toggleGenre(id: number) {
  const idx = form.value.genres?.indexOf(id)
  if (idx === undefined || idx === -1) {
    if (!form.value.genres) form.value.genres = []
    form.value.genres.push(id)
  } else {
    form.value.genres.splice(idx, 1)
  }
}

function getMediaTypeLabel(t: string) {
  if (t === 'movie') return '电影'
  if (t === 'tv') return '剧集'
  return '全部'
}
</script>

<template>
  <v-container fluid class="pa-6">
    <!-- 页头 -->
    <div class="d-flex flex-wrap align-center mb-6 ga-3">
      <div class="flex-grow-1">
        <h1 class="text-h5 font-weight-bold">标签规则</h1>
        <p class="text-caption text-medium-emphasis mt-1">
          配置自动标签规则，根据国家、类型、年份等条件自动为条目打标签 · 共 {{ rules.length }} 条规则
        </p>
      </div>
      <div class="d-flex ga-2 flex-wrap">
        <v-btn color="info" variant="tonal" size="small" prepend-icon="mdi-help-circle-outline" @click="showExplanation = true">
          规则说明
        </v-btn>
        <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-plus" @click="openAdd">
          新建规则
        </v-btn>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="isLoading && !rules.length" class="text-center pa-8">
      <v-progress-circular indeterminate color="primary" size="40" />
      <p class="mt-3 text-medium-emphasis">加载中...</p>
    </div>

    <!-- 规则卡片列表 -->
    <v-row v-if="rules.length" density="compact">
      <v-col v-for="rule in rules" :key="rule.id" cols="12" sm="6" md="4">
        <v-card variant="outlined" rounded="xl" class="pa-4 h-100">
          <div class="d-flex align-start mb-2">
            <div class="flex-grow-1">
              <div class="text-subtitle-2 font-weight-bold">{{ rule.name }}</div>
              <v-chip size="small" variant="tonal" color="primary" label class="mt-1">
                <v-icon start size="x-small">mdi-tag</v-icon>{{ rule.tag }}
              </v-chip>
            </div>
            <v-chip size="x-small" variant="tonal" label class="ml-2">{{ getMediaTypeLabel(rule.media_type) }}</v-chip>
          </div>

          <div class="text-caption text-medium-emphasis mt-2">
            <div v-if="rule.countries?.length">
              <v-icon size="x-small" start>mdi-earth</v-icon>
              国家: {{ rule.countries.map(c => getCountryName(c)).join(', ') }}
            </div>
            <div v-if="rule.genres?.length">
              <v-icon size="x-small" start>mdi-filmstrip</v-icon>
              类型: {{ rule.genres.map(g => getGenreName(g)).join(', ') }}
            </div>
            <div v-if="rule.year">
              <v-icon size="x-small" start>mdi-calendar</v-icon>
              年份: {{ rule.year }}
            </div>
            <div class="d-flex ga-2 mt-1">
              <v-chip v-if="rule.strict_match" size="x-small" variant="tonal" color="warning" label>严格匹配</v-chip>
              <v-chip v-if="rule.negative_match" size="x-small" variant="tonal" color="error" label>反向匹配</v-chip>
            </div>
          </div>

          <v-divider class="my-3" />
          <div class="d-flex justify-end ga-2">
            <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-pencil" @click="openEdit(rule)">编辑</v-btn>
            <v-btn size="small" variant="tonal" color="error" prepend-icon="mdi-delete-outline" @click="handleDelete(rule.id!, rule.name)">删除</v-btn>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- 空状态 -->
    <v-card v-else-if="!isLoading" variant="outlined" rounded="xl" class="pa-8">
      <div class="text-center">
        <v-icon size="64" color="grey-lighten-1">mdi-tag-off-outline</v-icon>
        <h3 class="text-h6 mt-3 mb-2">暂无标签规则</h3>
        <p class="text-caption text-medium-emphasis mb-4">
          创建标签规则以自动为影视条目打上标签
        </p>
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openAdd">
          新建第一条规则
        </v-btn>
      </div>
    </v-card>

    <!-- 规则说明对话框 -->
    <v-dialog v-model="showExplanation" max-width="900" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-help-circle-outline" class="mr-2" />
          标签规则匹配说明
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showExplanation = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="tag-rules-explanation pa-6">
          <div v-html="explanationHtml"></div>
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showExplanation = false">关闭</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 新建/编辑对话框 -->
    <v-dialog v-model="showDialog" max-width="560" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon :icon="isEditing ? 'mdi-pencil' : 'mdi-plus'" class="mr-2" />
          {{ isEditing ? '编辑规则' : '新建规则' }}
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-text-field v-model="form.name" label="规则名称 *" density="compact" variant="outlined" />
          <v-text-field v-model="form.tag" label="标签 *" density="compact" variant="outlined" hint="匹配后自动打的标签" />

          <v-select v-model="form.media_type" :items="mediaTypeOptions" item-title="title" item-value="value"
            label="媒体类型" density="compact" variant="outlined" />

          <div class="mb-4">
            <div class="text-body-2 mb-2">国家/地区</div>
            <div class="tag-chip-scroll d-flex flex-wrap ga-1">
              <v-chip v-for="c in countries" :key="c.iso_3166_1"
                size="small" :variant="form.countries?.includes(c.iso_3166_1) ? 'flat' : 'tonal'"
                :color="form.countries?.includes(c.iso_3166_1) ? 'primary' : 'default'"
                class="ma-1" @click="toggleCountry(c.iso_3166_1)">
                {{ c.native_name }}
              </v-chip>
            </div>
          </div>

          <div class="mb-4">
            <div class="text-body-2 mb-2">类型</div>
            <div class="scroll-y-200 d-flex flex-wrap ga-1">
              <v-chip v-for="g in genres" :key="g.id"
                size="small" :variant="form.genres?.includes(g.id) ? 'flat' : 'tonal'"
                :color="form.genres?.includes(g.id) ? 'primary' : 'default'"
                class="ma-1" @click="toggleGenre(g.id)">
                {{ g.name }}
              </v-chip>
            </div>
          </div>

          <v-text-field v-model="form.year" label="年份" density="compact" variant="outlined"
            placeholder="2024 或 2020-2025" />

          <v-checkbox v-model="form.strict_match" label="严格匹配（所有条件必须同时满足）" density="compact" hide-details />
          <v-checkbox v-model="form.negative_match" label="反向匹配（匹配到的条目不打此标签）" density="compact" hide-details />
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

<style scoped>
/* 国家/地区标签选择区滚动 */
.tag-chip-scroll {
  max-height: 180px;
  overflow-y: auto;
}
</style>

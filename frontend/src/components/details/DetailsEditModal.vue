<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDetailsStore, useAiStore } from '@/stores'
import { testTranslationApi } from '@/api/ai'
import { useNotification } from '@/composables'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const store = useDetailsStore()
const aiStore = useAiStore()
const { notify } = useNotification()

const isMovie = computed(() => store.currentItemType === 'tmdb-movies2')

const formData = ref<any>({})
const formTags = ref<string[]>([])
const formGenres = ref<string[]>([])
const isTranslating = ref<Record<string, boolean>>({})

// 弹框打开时填充表单数据
watch(() => props.modelValue, (open) => {
  if (open && store.itemDetails?.full_metadata) {
    const details = store.itemDetails
    formData.value = JSON.parse(JSON.stringify(details.full_metadata))
    if (formData.value.id) formData.value.id = Number(formData.value.id)
    if (formData.value.year) formData.value.year = Number(formData.value.year)
    const cleanDate = (d: any) => (d && typeof d === 'string' && d.length >= 10) ? d.substring(0, 10) : null
    if (formData.value.release_date !== undefined) formData.value.release_date = cleanDate(formData.value.release_date)
    if (formData.value.first_air_date !== undefined) formData.value.first_air_date = cleanDate(formData.value.first_air_date)
    if (formData.value.last_air_date !== undefined) formData.value.last_air_date = cleanDate(formData.value.last_air_date)
    formTags.value = details.tags ? [...details.tags] : []
    formGenres.value = details.full_metadata.genres ? details.full_metadata.genres.map((g: any) => g.name) : []
  }
})

const statusOptions = [
  { title: '已完结 (Ended)', value: 'Ended' },
  { title: '连载中 (Returning Series)', value: 'Returning Series' },
  { title: '已取消 (Canceled)', value: 'Canceled' },
  { title: '制作中 (In Production)', value: 'In Production' },
  { title: '计划中 (Planned)', value: 'Planned' },
  { title: '已上映 (Released)', value: 'Released' },
  { title: '后期制作 (Post Production)', value: 'Post Production' },
  { title: '试播集 (Pilot)', value: 'Pilot' },
]

async function handleAiTranslate(field: string, context: string) {
  const text = formData.value[field]
  if (!text) { notify('提示', '没有可翻译的内容', 'warning'); return }
  if (!aiStore.config.enabled) { notify('提示', '请先在设置中开启 AI 服务', 'warning'); return }
  isTranslating.value[field] = true
  try {
    const meta = store.itemDetails?.full_metadata
    const extra_info = {
      item_name: meta?.name || meta?.title || store.itemDetails?.name,
      item_id: store.currentItemId, item_type: store.currentItemType,
      item_genres: meta?.genres?.map((g: any) => g.name).join(', '),
      original_language: meta?.original_language,
    }
    const res = await testTranslationApi(text, context, extra_info)
    if (res.translated) { formData.value[field] = res.translated; notify('翻译完成', '', 'success') }
  } catch (e: any) { notify('翻译失败', e.message || '未知错误', 'error') }
  finally { isTranslating.value[field] = false }
}

async function handleSave() {
  const dataToSave = { ...formData.value }
  dataToSave.genres = formGenres.value.join(',')
  dataToSave.tags = formTags.value
  // 先关闭弹框，再异步保存（saveMetadata 内部会自动 loadDetails 刷新数据）
  emit('update:modelValue', false)
  const success = await store.saveMetadata(dataToSave)
  if (success) notify('保存成功', '', 'success')
  else notify('保存失败', '', 'error')
}

const newTag = ref('')
function addTag() { const t = newTag.value.trim(); if (t && !formTags.value.includes(t)) { formTags.value.push(t); newTag.value = '' } }
function removeTag(index: number) { formTags.value.splice(index, 1) }

const newGenre = ref('')
function addGenre() { const g = newGenre.value.trim(); if (g && !formGenres.value.includes(g)) { formGenres.value.push(g); newGenre.value = '' } }
function removeGenre(index: number) { formGenres.value.splice(index, 1) }
</script>

<template>
  <v-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" max-width="700" scrollable>
    <v-card rounded="xl">
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-pencil" class="mr-2" />
        编辑元数据
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="emit('update:modelValue', false)" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <v-form @submit.prevent="handleSave">
          <v-text-field v-model="formData[isMovie ? 'title' : 'name']" :label="isMovie ? '电影标题' : '剧集标题'" density="compact" variant="outlined" class="mb-2">
            <template #append-inner>
              <v-btn :loading="isTranslating[isMovie ? 'title' : 'name']" icon size="x-small" variant="text" @click="handleAiTranslate(isMovie ? 'title' : 'name', isMovie ? 'movie_title' : 'series_title')">
                <v-icon size="small">mdi-translate</v-icon>
              </v-btn>
            </template>
          </v-text-field>
          <v-text-field v-model="formData[isMovie ? 'original_title' : 'original_name']" label="原始标题" density="compact" variant="outlined" class="mb-2" />
          <v-textarea v-model="formData.overview" label="简介" density="compact" variant="outlined" rows="4" auto-grow class="mb-2">
            <template #append-inner>
              <v-btn :loading="isTranslating['overview']" icon size="x-small" variant="text" @click="handleAiTranslate('overview', isMovie ? 'movie_overview' : 'series_overview')">
                <v-icon size="small">mdi-translate</v-icon>
              </v-btn>
            </template>
          </v-textarea>
          <v-row>
            <v-col cols="6">
              <v-text-field v-model="formData.tagline" label="宣传语" density="compact" variant="outlined" />
            </v-col>
            <v-col cols="6">
              <v-select v-model="formData.status" :items="statusOptions" item-title="title" item-value="value" label="状态" density="compact" variant="outlined" />
            </v-col>
          </v-row>
          <v-row>
            <v-col cols="6">
              <v-text-field v-model="formData[isMovie ? 'release_date' : 'first_air_date']" :label="isMovie ? '上映日期' : '首播日期'" density="compact" variant="outlined" placeholder="YYYY-MM-DD" />
            </v-col>
            <v-col v-if="!isMovie" cols="6">
              <v-text-field v-model="formData.last_air_date" label="完结日期" density="compact" variant="outlined" placeholder="YYYY-MM-DD" />
            </v-col>
          </v-row>
          <v-text-field v-model.number="formData.vote_average" label="评分" type="number" step="0.1" min="0" max="10" density="compact" variant="outlined" class="mb-4" />

          <div class="text-caption text-medium-emphasis mb-2">类型</div>
          <div class="d-flex flex-wrap ga-1 mb-2">
            <v-chip v-for="(g, i) in formGenres" :key="i" size="small" closable @click:close="removeGenre(i)" variant="tonal" label>{{ g }}</v-chip>
          </div>
          <div class="d-flex align-center ga-2 mb-4">
            <v-text-field v-model="newGenre" density="compact" variant="outlined" placeholder="添加类型" hide-details class="flex-fill mw-300px" @keyup.enter="addGenre" />
            <v-btn density="compact" @click="addGenre" icon="mdi-plus" variant="tonal" flat />
          </div>

          <div class="text-caption text-medium-emphasis mb-2">本地标签</div>
          <div class="d-flex flex-wrap ga-1 mb-2">
            <v-chip v-for="(t, i) in formTags" :key="i" size="small" closable @click:close="removeTag(i)" variant="tonal" label>{{ t }}</v-chip>
          </div>
          <div class="d-flex align-center ga-2 mb-4">
            <v-text-field v-model="newTag" density="compact" variant="outlined" placeholder="添加标签" hide-details class="flex-fill mw-300px" @keyup.enter="addTag" />
            <v-btn density="compact" @click="addTag" icon="mdi-plus" variant="tonal" flat />
          </div>
        </v-form>
      </v-card-text>
      <v-divider />
      <v-card-actions>
        <v-spacer />
        <v-btn type="button" variant="tonal" color="grey" prepend-icon="mdi-close" @click="emit('update:modelValue', false)">取消</v-btn>
        <v-btn type="button" color="primary" variant="tonal" prepend-icon="mdi-check" @click="handleSave" :loading="store.isLoading">保存</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

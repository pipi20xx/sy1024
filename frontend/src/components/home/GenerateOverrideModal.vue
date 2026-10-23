<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { manualGenerateTmdb, getBangumiPreview } from '@/api/override'
import { useNotification } from '@/composables'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const { notify } = useNotification()

const isVisible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const loading = ref(false)
const previewLoading = ref(false)

const subjectPreview = ref<{ title: string; episodes: any[] } | null>(null)
const selectedEps = ref<number[]>([])

const typeOptions = computed(() => {
  if (model.value.source === 'tmdb') {
    return [
      { title: '电影', value: 'movie' },
      { title: '电视剧', value: 'tv' },
      { title: '单季', value: 'season' },
      { title: '单集', value: 'episode' },
    ]
  } else {
    return [
      { title: '番组 (Subject)', value: 'tv' },
      { title: '单集 (Episode)', value: 'episode' },
    ]
  }
})

const model = ref({
  source: 'tmdb' as 'tmdb' | 'bangumi',
  source_item_type: 'tv' as 'movie' | 'tv' | 'season' | 'episode',
  target_item_type: 'tv' as 'movie' | 'tv',
  source_tmdb_id: '',
  target_tmdb_id: '',
  source_season: 1,
  target_season: 1,
  source_episode: 1,
  target_episode: 1,
  overwrite: true,
  recursive: false,
  trigger_emby_refresh: false,
  lang: 'zh-CN',
})

watch(() => model.value.source_item_type, (newVal) => {
  if (newVal === 'movie') model.value.target_item_type = 'movie'
  else if (['tv', 'season', 'episode'].includes(newVal)) model.value.target_item_type = 'tv'
})

watch(() => model.value.source_tmdb_id, (newVal) => {
  if (newVal && !model.value.target_tmdb_id) {
    model.value.target_tmdb_id = newVal
  }
})

watch([() => model.value.source, () => model.value.source_tmdb_id], () => {
  subjectPreview.value = null
  selectedEps.value = []
  if (model.value.source === 'bangumi' && model.value.source_item_type === 'season') {
    model.value.source_item_type = 'tv'
  }
})

async function handleFetchBangumiPreview() {
  if (!model.value.source_tmdb_id) return
  previewLoading.value = true
  try {
    const data = await getBangumiPreview(parseInt(model.value.source_tmdb_id))
    subjectPreview.value = data
    notify('已获取', data.title, 'success')
  } catch (e: any) {
    notify('获取失败', e.message, 'error')
  } finally {
    previewLoading.value = false
  }
}

function selectAllMainEps() {
  if (subjectPreview.value) {
    selectedEps.value = subjectPreview.value.episodes
      .filter(ep => ep.type === 0 || ep.type === 6)
      .map(ep => ep.sort)
  }
}

async function handleSubmit() {
  if (!model.value.source_tmdb_id || !model.value.target_tmdb_id) {
    notify('提示', '请输入源 ID 和目标 ID', 'warning')
    return
  }
  loading.value = true
  try {
    if (model.value.source === 'bangumi' && model.value.source_item_type === 'episode' && selectedEps.value.length > 0) {
      const total = selectedEps.value.length
      for (let i = 0; i < total; i++) {
        const epSort = selectedEps.value[i]
        await manualGenerateTmdb({
          ...model.value,
          source_item_type: 'episode',
          source_episode: epSort,
          target_episode: epSort,
          target_item_type: model.value.target_item_type,
          trigger_emby_refresh: false,
        })
      }
      if (model.value.trigger_emby_refresh) {
        await manualGenerateTmdb({
          ...model.value,
          source_item_type: 'tv',
          trigger_emby_refresh: true,
          overwrite: false,
        })
      }
      notify('批量生成成功', `共生成 ${total} 集`, 'success')
    } else {
      await manualGenerateTmdb({
        ...model.value,
        source_season: ['season', 'episode'].includes(model.value.source_item_type) ? model.value.source_season : undefined,
        target_season: ['tv', 'season', 'episode'].includes(model.value.source_item_type) ? model.value.target_season : undefined,
        source_episode: model.value.source_item_type === 'episode' ? model.value.source_episode : undefined,
        target_episode: model.value.source_item_type === 'episode' ? model.value.target_episode : undefined,
      })
      notify('生成成功', '', 'success')
    }
    isVisible.value = false
  } catch (e: any) {
    notify('生成失败', e.message, 'error')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <v-dialog v-model="isVisible" max-width="720" scrollable>
    <v-card rounded="xl">
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-flash" class="mr-2" />
        一键生成 Override
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="isVisible = false" />
      </v-card-title>
      <v-divider />

      <v-card-text class="pt-4">
        <!-- 源切换 -->
        <div class="text-center mb-4">
          <v-btn-toggle v-model="model.source" mandatory color="primary" variant="tonal" divided>
            <v-btn value="tmdb">The Movie DB (TMDB)</v-btn>
            <v-btn value="bangumi">Bangumi (番组计划)</v-btn>
          </v-btn-toggle>
        </div>

        <!-- 项目类型 + 源 ID -->
        <v-row density="compact" class="mb-4">
          <v-col cols="4">
            <v-select v-model="model.source_item_type" :items="typeOptions" item-title="title" item-value="value"
              label="项目类型" density="compact" variant="outlined" />
          </v-col>
          <v-col :cols="model.source === 'bangumi' ? 5 : 8">
            <v-text-field v-model="model.source_tmdb_id"
              :label="model.source === 'tmdb' ? '源 TMDB ID' : '源 Bangumi ID'"
              density="compact" variant="outlined" placeholder="输入 ID" />
          </v-col>
          <v-col v-if="model.source === 'bangumi'" cols="3" class="d-flex align-center">
            <v-btn block variant="tonal" color="info" :loading="previewLoading" @click="handleFetchBangumiPreview"
              height="40" class="btn-caption">
              获取单集列表
            </v-btn>
          </v-col>
        </v-row>

        <!-- Bangumi 单集选择 -->
        <v-card v-if="model.source === 'bangumi' && subjectPreview && model.source_item_type === 'episode'"
          variant="outlined" rounded="xl" class="mb-4 pa-3">
          <div class="d-flex align-center mb-2">
            <v-chip size="small" variant="tonal" color="info" class="mr-2">{{ subjectPreview.title }}</v-chip>
            <span class="text-body-2">选择要生成的集 (已选 {{ selectedEps.length }})</span>
            <v-spacer />
            <v-btn size="small" variant="tonal" @click="selectAllMainEps">全选正片</v-btn>
          </div>
          <div class="scroll-y-200">
            <v-checkbox v-for="ep in subjectPreview.episodes" :key="ep.id" v-model="selectedEps"
              :value="ep.sort" density="compact" hide-details class="py-0">
              <template #label>
                <v-chip size="x-small" :color="ep.type === 0 ? 'success' : undefined" variant="tonal" label class="mr-1">
                  EP{{ ep.sort }}
                </v-chip>
                <span class="text-body-2">{{ ep.name }}</span>
              </template>
            </v-checkbox>
          </div>
        </v-card>

        <!-- 目标配置 -->
        <v-row density="compact">
          <v-col cols="6">
            <div class="text-subtitle-2 font-weight-bold mb-2">存储目标</div>
            <v-btn-toggle v-model="model.target_item_type" mandatory color="primary" variant="tonal" divided
              density="compact" class="mb-3">
              <v-btn value="tv">剧集 (tmdb-tv)</v-btn>
              <v-btn value="movie">电影 (tmdb-movies2)</v-btn>
            </v-btn-toggle>
            <v-text-field v-model="model.target_tmdb_id" label="目标 TMDB ID (文件夹名)"
              density="compact" variant="outlined" placeholder="本地文件夹 ID" />
            <template v-if="['tv', 'season', 'episode'].includes(model.source_item_type)">
              <v-text-field v-model.number="model.target_season" label="存为季号" type="number"
                density="compact" variant="outlined" class="mt-3" />
              <v-text-field v-if="model.source_item_type === 'episode' && selectedEps.length <= 1"
                v-model.number="model.target_episode" label="存为集号" type="number"
                density="compact" variant="outlined" class="mt-3" />
            </template>
          </v-col>
          <v-col cols="6">
            <div class="text-subtitle-2 font-weight-bold mb-2">选项</div>
            <v-switch v-model="model.overwrite" label="覆盖现有字段" density="compact" hide-details color="primary" />
            <v-switch v-if="model.source_item_type === 'tv' || (model.source === 'tmdb' && model.source_item_type === 'season')"
              v-model="model.recursive" label="递归生成 (全剧/全季)" density="compact" hide-details color="primary" />
            <v-switch v-model="model.trigger_emby_refresh" label="生成后刷新 Emby" density="compact" hide-details color="primary" />
          </v-col>
        </v-row>
      </v-card-text>

      <v-divider />
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="isVisible = false">取消</v-btn>
        <v-btn color="warning" variant="tonal" :loading="loading"
          :disabled="model.source === 'bangumi' && model.source_item_type === 'episode' && selectedEps.length === 0"
          prepend-icon="mdi-flash" @click="handleSubmit">
          {{ selectedEps.length > 1 ? `批量生成 ${selectedEps.length} 个集` : '立即生成' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

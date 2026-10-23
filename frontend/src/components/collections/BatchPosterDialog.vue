<script setup lang="ts">
import { ref, watch, onMounted, reactive } from 'vue'
import { generateCollectionPoster, getAvailableFonts, batchGenerateCollectionPosterBg } from '@/api/collectionPoster'
import type { GeneratePosterRequest, PosterLayers } from '@/api/collectionPoster'
import type { Collection } from '@/types/collection'
import { getCollectionDetails } from '@/api/collections'
import { useNotification } from '@/composables'
import PosterPreviewCanvas from './PosterPreviewCanvas.vue'

const props = defineProps<{
  modelValue: boolean
  collections: Collection[]
}>()

const emit = defineEmits<{ 'update:modelValue': [boolean]; done: [] }>()
const { notify } = useNotification()

// ── 状态 ──
const isGenerating = ref(false)
const previewLayers = ref<PosterLayers | null>(null)
const fontOptions = ref<{ title: string; value: string }[]>([])
let lastRequestId = 0
const currentSeed = ref<number | undefined>(undefined)
const canvasRef = ref<InstanceType<typeof PosterPreviewCanvas> | null>(null)

// 样本合集（取第一个用于预览）
const sampleCollection = ref<Collection | null>(null)
const sampleItemIds = ref<string[]>([])
const sampleMovieIds = ref<string[]>([])
const sampleSeriesIds = ref<string[]>([])
const sampleTitlesMap = ref<Record<string, string[]> | undefined>()

// ── 参数 ──
const params = reactive({
  style_type: 'circle_focus',
  title_zh: '',
  title_en: '',
  collection_names_str: '',
  show_zh: true,
  show_en: true,
  font_zh: '',
  font_en: '',
  zh_font_size_ratio: 1.0,
  en_font_size_ratio: 1.0,
  resolution_scale: 1.0,
})

const styleOptions = [
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

// ── 初始化 ──
onMounted(async () => {
  try {
    const res = await getAvailableFonts()
    fontOptions.value = res.fonts.map(f => ({ title: f, value: f }))
    const zhFont = fontOptions.value.find(f => f.value.includes('_zh'))
    if (zhFont) {
      params.font_zh = zhFont.value
      const baseName = zhFont.value.split('_zh')[0]
      const enFont = fontOptions.value.find(f => f.value.startsWith(baseName) && f.value.includes('_en'))
      params.font_en = enFont?.value || fontOptions.value[0]?.value || ''
    } else {
      params.font_zh = fontOptions.value[0]?.value || ''
      params.font_en = fontOptions.value[0]?.value || ''
    }
  } catch (e) {
    console.error('加载字体列表失败', e)
  }
})

watch(() => props.modelValue, async (newVal) => {
  if (newVal) {
    previewLayers.value = null
    params.collection_names_str = ''

    // 取第一个合集做预览样本
    if (props.collections.length > 0) {
      const sample = props.collections[0]
      params.title_zh = sample.name || ''
      params.title_en = sample.name || ''
      sampleCollection.value = sample

      try {
        const details = await getCollectionDetails(sample.filename)
        const movies = details.movies || []
        const series = details.series || []
        sampleItemIds.value = [...movies, ...series].map((i: any) => String(i.id))
        sampleMovieIds.value = movies.map((m: any) => String(m.id))
        sampleSeriesIds.value = series.map((s: any) => String(s.id))
        const map: Record<string, string[]> = {}
        for (const m of movies) { if (m.id && m.name) map[String(m.id)] = [m.name] }
        for (const s of series) { if (s.id && s.name) map[String(s.id)] = [s.name] }
        sampleTitlesMap.value = Object.keys(map).length ? map : undefined
        // 自动生成预览
        handleGeneratePreview()
      } catch (e) {
        console.error('加载样本合集详情失败', e)
      }
    }
  }
})

// ── 操作 ──
async function handleGeneratePreview() {
  if (!sampleCollection.value) return

  const requestId = ++lastRequestId
  isGenerating.value = true
  currentSeed.value = Math.floor(Math.random() * 1000000)

  try {
    const req: GeneratePosterRequest = {
      collection_id: sampleCollection.value.filename,
      item_ids: sampleItemIds.value,
      movie_ids: sampleMovieIds.value,
      series_ids: sampleSeriesIds.value,
      titles_map: sampleTitlesMap.value,
      style_type: params.style_type,
      title_zh: params.title_zh,
      title_en: params.title_en,
      show_zh: params.show_zh,
      show_en: params.show_en,
      font_zh: params.font_zh,
      font_en: params.font_en,
      zh_font_size_ratio: params.zh_font_size_ratio,
      en_font_size_ratio: params.en_font_size_ratio,
      offset_x: 0,
      offset_y: 0,
      resolution_scale: 1.0,
      seed: currentSeed.value,
      return_layers: true,
    }
    const result = await generateCollectionPoster(req)
    if (requestId !== lastRequestId) return
    if (typeof result === 'object' && 'base' in result) {
      previewLayers.value = result as PosterLayers
    }
  } catch {
    if (requestId === lastRequestId) notify('生成预览失败', '', 'error')
  } finally {
    if (requestId === lastRequestId) isGenerating.value = false
  }
}

async function handleBatchGenerate() {
  const hasManualInput = params.collection_names_str && params.collection_names_str.trim().length > 0
  if (!hasManualInput && props.collections.length === 0) {
    notify('没有可处理的合集', '', 'warning')
    return
  }

  const finalOffsetX = Math.round(canvasRef.value!.visualOffset.x * canvasRef.value!.scaleFactor)
  const finalOffsetY = Math.round(canvasRef.value!.visualOffset.y * canvasRef.value!.scaleFactor)
  const targetFilenames = hasManualInput ? [] : props.collections.map(c => c.filename)

  try {
    await batchGenerateCollectionPosterBg({
      collection_filenames: targetFilenames,
      collection_names_str: hasManualInput ? params.collection_names_str : undefined,
      style_type: params.style_type,
      show_zh: params.show_zh,
      show_en: params.show_en,
      font_zh: params.font_zh,
      font_en: params.font_en,
      zh_font_size_ratio: params.zh_font_size_ratio,
      en_font_size_ratio: params.en_font_size_ratio,
      offset_x: finalOffsetX,
      offset_y: finalOffsetY,
      resolution_scale: params.resolution_scale,
      seed: undefined,
    })
    notify('批量生成任务已启动，请查看任务进度', '', 'success')
    emit('update:modelValue', false)
    emit('done')
  } catch (e: any) {
    notify('启动批量生成失败', e.message || '', 'error')
  }
}

function handleClose() {
  emit('update:modelValue', false)
}
</script>

<template>
  <v-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" max-width="1100" width="95vw" scrollable>
    <v-card rounded="xl" :height="620">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-image-multiple" class="mr-2" />
        批量生成海报 (共 {{ collections.length }} 个合集)
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="handleClose" />
      </v-card-title>

      <v-divider />

      <div class="poster-dialog-body d-flex">
        <!-- 左侧：设置 -->
        <div class="flex-grow-1 pa-4 overflow-y-auto">
          <!-- 提示 -->
          <v-alert type="info" variant="tonal" density="compact" class="mb-3 text-caption">
            正在使用第一个合集 "{{ sampleCollection?.name || '...' }}" 作为样式预览样本。批量生成时，每个合集将使用其自己的随机种子。
          </v-alert>

          <!-- 生成范围 -->
          <div class="text-caption font-weight-bold text-medium-emphasis mb-1">生成范围</div>
          <v-textarea
            v-model="params.collection_names_str"
            placeholder="输入合集名称，用逗号分隔（如：漫威宇宙，哈利波特）。留空则处理列表中的所有合集。"
            density="compact"
            variant="outlined"
            :rows="2"
            class="mb-2"
          />

          <v-row density="compact">
            <v-col cols="6">
              <v-select v-model="params.style_type" :items="styleOptions" label="样式风格" density="compact" variant="outlined" />
            </v-col>
            <v-col cols="6">
              <v-select v-model="params.resolution_scale" :items="resolutionOptions" label="输出分辨率" density="compact" variant="outlined" />
            </v-col>
          </v-row>

          <div class="text-caption font-weight-bold text-medium-emphasis mt-2 mb-1">标题设置</div>
          <v-row density="compact">
            <v-col cols="6">
              <v-text-field v-model="params.title_zh" label="中文标题" density="compact" variant="outlined" />
            </v-col>
            <v-col cols="6">
              <v-text-field v-model="params.title_en" label="英文标题" density="compact" variant="outlined" />
            </v-col>
          </v-row>
          <div class="d-flex ga-4 mb-2">
            <v-checkbox v-model="params.show_zh" label="显示中文" density="compact" hide-details />
            <v-checkbox v-model="params.show_en" label="显示英文" density="compact" hide-details />
          </div>

          <div class="text-caption font-weight-bold text-medium-emphasis mt-2 mb-1">字体与排版</div>
          <v-row density="compact">
            <v-col cols="6">
              <v-select v-model="params.font_zh" :items="fontOptions" label="中文字体" density="compact" variant="outlined" />
            </v-col>
            <v-col cols="6">
              <v-select v-model="params.font_en" :items="fontOptions" label="英文字体" density="compact" variant="outlined" />
            </v-col>
          </v-row>
          <v-row density="compact">
            <v-col cols="6">
              <div class="text-caption mb-1">中文字号 ({{ params.zh_font_size_ratio }}x)</div>
              <v-slider v-model="params.zh_font_size_ratio" :min="0.5" :max="2.0" :step="0.1" thumb-label color="primary" track-color="grey-darken-1" />
            </v-col>
            <v-col cols="6">
              <div class="text-caption mb-1">英文字号 ({{ params.en_font_size_ratio }}x)</div>
              <v-slider v-model="params.en_font_size_ratio" :min="0.5" :max="2.0" :step="0.1" thumb-label color="primary" track-color="grey-darken-1" />
            </v-col>
          </v-row>

          <v-row density="compact" class="mt-2">
            <v-col cols="6">
              <v-btn block variant="tonal" color="primary" :loading="isGenerating" @click="handleGeneratePreview">
                <v-icon start>mdi-refresh</v-icon> 更新预览
              </v-btn>
            </v-col>
            <v-col cols="6">
              <v-btn block variant="tonal" color="success" :loading="isGenerating" @click="handleBatchGenerate">
                <v-icon start>mdi-play</v-icon> 开始批量生成
              </v-btn>
            </v-col>
          </v-row>
        </div>

        <!-- 右侧：预览 -->
        <v-sheet width="280" class="flex-shrink-0 d-flex align-center justify-center pa-4 bg-surface-variant" rounded="0">
          <PosterPreviewCanvas
            ref="canvasRef"
            :layers="previewLayers"
            :is-generating="isGenerating"
            :seed="currentSeed"
          />
        </v-sheet>
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped>
/* 弹窗主体高度：标题栏(65px)以下全部留给设置区与预览区 */
.poster-dialog-body {
  height: calc(100% - 65px);
}
</style>

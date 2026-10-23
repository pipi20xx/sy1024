<script setup lang="ts">
import { ref, watch, onMounted, reactive } from 'vue'
import { generateCollectionPoster, getAvailableFonts } from '@/api/collectionPoster'
import type { GeneratePosterRequest, PosterLayers } from '@/api/collectionPoster'
import { uploadCollectionImage } from '@/api/collections'
import { useNotification } from '@/composables'
import PosterPreviewCanvas from './PosterPreviewCanvas.vue'

const props = defineProps<{
  modelValue: boolean
  collectionId?: string
  itemIds?: string[]
  movieIds?: string[]
  seriesIds?: string[]
  titlesMap?: Record<string, string[]>
  initialTitleZh?: string
  initialTitleEn?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [boolean]; saved: [] }>()
const { notify } = useNotification()

// ── 状态 ──
const isGenerating = ref(false)
const previewLayers = ref<PosterLayers | null>(null)
const fontOptions = ref<{ title: string; value: string }[]>([])
let lastRequestId = 0
const currentSeed = ref<number | undefined>(undefined)
const canvasRef = ref<InstanceType<typeof PosterPreviewCanvas> | null>(null)

// ── 参数 ──
const params = reactive({
  style_type: 'circle_focus',
  title_zh: '',
  title_en: '',
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
    // 自动选择中英文字体
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

watch(() => props.modelValue, (newVal) => {
  if (newVal) {
    params.title_zh = props.initialTitleZh || ''
    params.title_en = props.initialTitleEn || ''
    previewLayers.value = null
  }
})

// ── 操作 ──
async function handleGeneratePreview() {
  const requestId = ++lastRequestId
  isGenerating.value = true
  currentSeed.value = Math.floor(Math.random() * 1000000)

  try {
    const req: GeneratePosterRequest = {
      collection_id: props.collectionId,
      item_ids: props.itemIds,
      movie_ids: props.movieIds,
      series_ids: props.seriesIds,
      titles_map: props.titlesMap,
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
  } catch (e) {
    if (requestId === lastRequestId) notify('生成预览失败', '', 'error')
  } finally {
    if (requestId === lastRequestId) isGenerating.value = false
  }
}

async function handleSavePoster() {
  isGenerating.value = true
  try {
    const { visualOffset, scaleFactor } = canvasRef.value!
    const finalOffsetX = Math.round(visualOffset.x * scaleFactor)
    const finalOffsetY = Math.round(visualOffset.y * scaleFactor)

    const req: GeneratePosterRequest = {
      ...params,
      collection_id: props.collectionId,
      item_ids: props.itemIds,
      movie_ids: props.movieIds,
      series_ids: props.seriesIds,
      titles_map: props.titlesMap,
      offset_x: finalOffsetX,
      offset_y: finalOffsetY,
      seed: currentSeed.value,
      return_layers: false,
    }

    const result = await generateCollectionPoster(req) as any

    // 后端可能返回纯 base64 字符串，也可能返回 JSON 包裹的字符串
    let base64Data: string | null = null
    if (typeof result === 'string') {
      base64Data = result
    } else if (result && typeof result === 'object') {
      // 兼容: 后端可能返回 { image: "base64..." } 或 { data: "base64..." } 或 { poster: "base64..." }
      base64Data = result.image || result.data || result.poster || result.base64 || null
    }

    if (base64Data) {
      const byteString = atob(base64Data)
      const ab = new ArrayBuffer(byteString.length)
      const ia = new Uint8Array(ab)
      for (let i = 0; i < byteString.length; i++) ia[i] = byteString.charCodeAt(i)
      const blob = new Blob([ab], { type: 'image/jpeg' })
      const file = new File([blob], 'poster.jpg', { type: 'image/jpeg' })

      if (props.collectionId) {
        await uploadCollectionImage(props.collectionId, 'poster', file)
        notify('海报已生成并上传', '', 'success')
        emit('saved')
      }
      emit('update:modelValue', false)
    } else {
      console.error('Unexpected poster generation result:', result)
      notify('保存海报失败', '后端返回格式异常', 'error')
    }
  } catch (e: any) {
    console.error('保存海报失败:', e)
    notify('保存海报失败', e.message || '', 'error')
  } finally {
    isGenerating.value = false
  }
}

function handleClose() {
  emit('update:modelValue', false)
}
</script>

<template>
  <v-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" max-width="1100" width="95vw" scrollable>
    <v-card rounded="xl" :height="680">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-image-edit" class="mr-2" />
        合集海报生成器
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="handleClose" />
      </v-card-title>

      <v-divider />

      <div class="poster-dialog-body d-flex">
        <!-- 左侧：设置 -->
        <div class="flex-grow-1 pa-4 overflow-y-auto">
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
              <v-btn block variant="tonal" color="success" :loading="isGenerating" :disabled="!previewLayers" @click="handleSavePoster">
                <v-icon start>mdi-content-save</v-icon> 保存海报
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

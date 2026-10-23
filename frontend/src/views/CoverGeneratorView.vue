<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api } from '@/api/client'
defineOptions({ name: 'CoverGeneratorView' })
import { useNotification } from '@/composables'

const { notify } = useNotification()

// State
const fonts = ref<{ title: string; value: string }[]>([])
const libraries = ref<{ title: string; value: string }[]>([])
const loading = ref(false)
const uploading = ref(false)
const generatedImage = ref<string | null>(null)
const activeTab = ref('basic')

const styleOptions = [
  { label: '单图样式 1', value: 'single_1', img: '/static/style_previews/single_1.jpg' },
  { label: '单图样式 2', value: 'single_2', img: '/static/style_previews/single_2.jpg' },
  { label: '多图九宫格', value: 'multi_1', img: '/static/style_previews/multi_1.jpg' },
  { label: '多图九宫图(动态)', value: 'multi_animated', img: '/static/style_previews/multi_animated.jpg' },
  { label: '背景轮播 (动态)', value: 'style_6_plus_1', img: '/static/style_previews/style_6_plus_1.jpg' },
  { label: '背景斜播 (动态)', value: 'style_9_plus_1', img: '/static/style_previews/style_9_plus_1.jpg' },
  { label: '横向轮播 (动态)', value: 'style_5_horizontal', img: '/static/style_previews/style_5_horizontal.jpg' },
]

const sortOptions = [
  { title: '随机 (Random)', value: 'Random' },
  { title: '添加日期 (Date Created)', value: 'DateCreated' },
  { title: '发行年份 (Production Year)', value: 'ProductionYear' },
  { title: '评分 (Community Rating)', value: 'CommunityRating' },
]

const animationFormatOptions = [
  { title: 'APNG (推荐 / 兼容性最好)', value: 'png' },
  { title: 'GIF (通用格式)', value: 'gif' },
  { title: 'WebP (高质量/小体积)', value: 'webp' },
]

interface FormState {
  library_ids: string[]
  style_type: string
  title_zh: string
  title_en: string
  font_zh: string
  font_en: string
  zh_font_size_ratio: number
  en_font_size_ratio: number
  blur_size: number
  color_ratio: number
  sort_by: string
  is_blur: boolean
  upload: boolean
  title_config: string
  use_primary_first: boolean
  animation_format: string
}

const formValue = ref<FormState>({
  library_ids: [],
  style_type: 'single_1',
  title_zh: '',
  title_en: '',
  font_zh: '',
  font_en: '',
  zh_font_size_ratio: 1.0,
  en_font_size_ratio: 1.0,
  blur_size: 50,
  color_ratio: 0.8,
  sort_by: 'Random',
  is_blur: false,
  upload: false,
  title_config: '',
  use_primary_first: false,
  animation_format: 'png',
})

const isMultiStyle = computed(() =>
  ['multi_1', 'multi_animated', 'style_6_plus_1', 'style_9_plus_1', 'style_5_horizontal'].includes(formValue.value.style_type),
)

onMounted(async () => {
  try {
    // 1. Fetch Config
    const savedConfig = await api.get<any>('/api/covers/config')
    if (savedConfig) {
      formValue.value = { ...formValue.value, ...savedConfig }
      formValue.value.library_ids = []
      formValue.value.upload = false
    }

    // 2. Fetch Fonts
    const dataFonts = await api.get<{ fonts: string[] }>('/api/covers/fonts')
    fonts.value = dataFonts.fonts.map((f: string) => ({ title: f, value: f }))

    if (!formValue.value.font_zh && fonts.value.length > 0) {
      formValue.value.font_zh = fonts.value[0].value
    }
    if (!formValue.value.font_en && fonts.value.length > 0) {
      formValue.value.font_en = fonts.value[0].value
    }

    // 3. Fetch Libraries
    const dataLibs = await api.get<{ libraries: any[] }>('/api/covers/libraries')
    libraries.value = dataLibs.libraries.map((l: any) => ({ title: l.Name, value: l.Id }))
  } catch (e: any) {
    notify('加载失败', e.message, 'error')
  }
})

function handleLibraryChange(value: string[]) {
  if (value.length === 1) {
    const selectedLib = libraries.value.find((l) => l.value === value[0])
    if (selectedLib) {
      formValue.value.title_zh = selectedLib.title
    }
  }
}

function selectStyle(styleValue: string) {
  formValue.value.style_type = styleValue
}

async function handleSaveConfig() {
  try {
    const saveData = { ...formValue.value }
    delete (saveData as any).library_ids
    delete (saveData as any).upload
    await api.post('/api/covers/config', saveData)
    notify('保存成功', '配置已保存', 'success')
  } catch (e: any) {
    notify('保存失败', e.message, 'error')
  }
}

async function handleGenerate(upload: boolean = false) {
  if (formValue.value.library_ids.length === 0) {
    notify('提示', '请至少选择一个媒体库', 'warning')
    return
  }

  if (!formValue.value.title_config && !formValue.value.title_zh) {
    notify('提示', '请输入中文标题或配置标题映射', 'warning')
    return
  }

  loading.value = true
  const payload = { ...formValue.value, upload }

  try {
    const data = await api.post<any>('/api/covers/generate', payload)

    if (data.image) {
      generatedImage.value = data.image
    }

    if (upload) {
      notify('成功', data.message || '已成功生成并上传', 'success')
    } else {
      notify('生成完成', '', 'success')
    }
  } catch (e: any) {
    notify('失败', e.message, 'error')
  } finally {
    loading.value = false
  }
}

async function handleManualUpload() {
  if (!generatedImage.value || formValue.value.library_ids.length !== 1) {
    notify('提示', '请选择单个媒体库并在生成预览后使用此功能', 'warning')
    return
  }

  uploading.value = true
  try {
    await api.post('/api/covers/upload', {
      library_id: formValue.value.library_ids[0],
      image: generatedImage.value,
    })
    notify('上传成功', '', 'success')
  } catch (e: any) {
    notify('上传失败', e.message, 'error')
  } finally {
    uploading.value = false
  }
}

function handleDownload() {
  if (!generatedImage.value) return
  const link = document.createElement('a')
  link.href = generatedImage.value
  link.download = `cover-${formValue.value.title_zh || 'generated'}.png`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}
</script>

<template>
  <v-container fluid class="pa-6">
    <div class="d-flex flex-wrap align-center mb-6 ga-3">
      <div class="flex-grow-1">
        <h1 class="text-h5 font-weight-bold">EMBY 封面生成器</h1>
        <p class="text-caption text-medium-emphasis mt-1">自动为 Emby 媒体库生成精美的合集封面</p>
      </div>
    </div>

    <v-row>
      <!-- 配置区 -->
      <v-col cols="12" md="6">
        <v-card variant="outlined" rounded="xl">
          <v-tabs v-model="activeTab" density="compact" color="primary">
            <v-tab value="basic">基础设置</v-tab>
            <v-tab value="style">样式调整</v-tab>
            <v-tab value="config">标题配置</v-tab>
          </v-tabs>
          <v-divider />

          <v-card-text class="pt-4">
            <v-window v-model="activeTab">
              <!-- 基础设置 -->
              <v-window-item value="basic">
                <v-select
                  v-model="formValue.library_ids"
                  :items="libraries"
                  multiple
                  chips
                  label="媒体库"
                  density="compact"
                  variant="outlined"
                  placeholder="选择 Emby 媒体库 (支持多选)"
                  class="mb-3"
                  @update:model-value="handleLibraryChange"
                />

                <div class="text-subtitle-2 font-weight-bold mb-2">封面样式</div>
                <v-row density="compact" class="mb-3">
                  <v-col v-for="style in styleOptions" :key="style.value" cols="4">
                    <div
                      class="thumb-select-wrapper cursor-pointer"
                      :class="{ 'thumb-select--selected': formValue.style_type === style.value }"
                      @click="selectStyle(style.value)"
                    >
                      <v-img :src="style.img" aspect-ratio="16/9" cover class="rounded-t-md" />
                      <div class="text-caption text-center pa-1">{{ style.label }}</div>
                      <transition name="fade-check">
                        <div v-if="formValue.style_type === style.value" class="thumb-select-check thumb-select-check--sm">
                          <v-icon size="16" icon="mdi-check-circle" />
                        </div>
                      </transition>
                    </div>
                  </v-col>
                </v-row>

                <v-select v-model="formValue.sort_by" :items="sortOptions" label="选图排序" density="compact" variant="outlined" class="mb-3" />
                <v-text-field v-model="formValue.title_zh" label="中文标题" density="compact" variant="outlined" placeholder="输入中文标题 (单库模式优先)" class="mb-3" />
                <v-text-field v-model="formValue.title_en" label="英文标题" density="compact" variant="outlined" placeholder="输入英文标题 (可选)" />
              </v-window-item>

              <!-- 样式调整 -->
              <v-window-item value="style">
                <v-select v-model="formValue.font_zh" :items="fonts" label="中文字体" density="compact" variant="outlined" class="mb-3" />
                <v-select v-model="formValue.font_en" :items="fonts" label="英文字体" density="compact" variant="outlined" class="mb-3" />

                <div class="text-caption mb-1">中文缩放 ({{ formValue.zh_font_size_ratio }}x)</div>
                <v-slider v-model="formValue.zh_font_size_ratio" :min="0.5" :max="2.0" :step="0.1" thumb-label color="primary" track-color="grey-darken-1" class="mb-2" />
                <div class="text-caption mb-1">英文缩放 ({{ formValue.en_font_size_ratio }}x)</div>
                <v-slider v-model="formValue.en_font_size_ratio" :min="0.5" :max="2.0" :step="0.1" thumb-label color="primary" track-color="grey-darken-1" class="mb-2" />
                <div class="text-caption mb-1">背景模糊度 ({{ formValue.blur_size }})</div>
                <v-slider v-model="formValue.blur_size" :min="0" :max="100" thumb-label color="primary" track-color="grey-darken-1" class="mb-2" />
                <div class="text-caption mb-1">颜色混合比 ({{ formValue.color_ratio }})</div>
                <v-slider v-model="formValue.color_ratio" :min="0" :max="1" :step="0.05" thumb-label color="primary" track-color="grey-darken-1" class="mb-2" />

                <v-switch v-if="isMultiStyle" v-model="formValue.is_blur" density="compact" hide-details color="primary" class="mb-2">
                  <template #label>启用模糊背景 <span class="text-caption text-medium-emphasis">(仅多图样式有效)</span></template>
                </v-switch>
                <v-switch v-model="formValue.use_primary_first" density="compact" hide-details color="primary" class="mb-2">
                  <template #label>优先使用海报 <span class="text-caption text-medium-emphasis">(竖向海报图而非横向背景图)</span></template>
                </v-switch>

                <v-select
                  v-if="['multi_animated', 'style_6_plus_1', 'style_9_plus_1', 'style_5_horizontal'].includes(formValue.style_type)"
                  v-model="formValue.animation_format"
                  :items="animationFormatOptions"
                  label="动画格式"
                  density="compact"
                  variant="outlined"
                />
              </v-window-item>

              <!-- 标题配置 -->
              <v-window-item value="config">
                <v-textarea
                  v-model="formValue.title_config"
                  label="标题映射配置"
                  variant="outlined"
                  placeholder="在此输入标题映射配置..."
                  :rows="10"
                  auto-grow
                />
              </v-window-item>
            </v-window>

            <v-divider class="my-4" />
            <div class="d-flex ga-2 flex-wrap align-center">
              <v-btn color="primary" variant="tonal" :loading="loading" @click="handleGenerate(false)" prepend-icon="mdi-image-outline">
                生成预览
              </v-btn>
              <v-btn color="warning" variant="tonal" :loading="loading" @click="handleGenerate(true)" prepend-icon="mdi-cloud-upload">
                生成并上传
              </v-btn>
              <v-spacer />
              <v-btn color="primary" variant="tonal" @click="handleSaveConfig" prepend-icon="mdi-content-save">
                保存配置
              </v-btn>
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- 预览区 -->
      <v-col cols="12" md="6">
        <v-card variant="outlined" rounded="xl" height="100%">
          <v-card-title class="d-flex align-center">
            <v-icon icon="mdi-eye-outline" class="mr-2" />
            预览
          </v-card-title>
          <v-divider />

          <v-card-text class="loading-state d-flex justify-center align-center">
            <div v-if="loading" class="text-center">
              <v-progress-circular indeterminate color="primary" size="64" />
              <p class="mt-4 text-medium-emphasis">正在处理...</p>
            </div>

            <div v-else-if="generatedImage" class="w-100">
              <v-img :src="generatedImage" contain class="preview-img" max-height="500" />
              <div class="d-flex justify-center ga-3 mt-4">
                <v-btn color="success" variant="tonal" prepend-icon="mdi-download" @click="handleDownload">下载预览图</v-btn>
                <v-btn
                  color="error"
                  variant="tonal"
                  prepend-icon="mdi-cloud-upload"
                  :loading="uploading"
                  :disabled="formValue.library_ids.length !== 1"
                  @click="handleManualUpload"
                >
                  上传到服务器
                </v-btn>
              </div>
              <div v-if="formValue.library_ids.length !== 1" class="text-caption text-medium-emphasis text-center mt-2">
                (手动上传仅支持单选媒体库)
              </div>
            </div>

            <div v-else class="text-center text-medium-emphasis">
              <v-icon size="64" color="grey-lighten-1">mdi-image-off-outline</v-icon>
              <p class="mt-3">请配置参数并点击生成</p>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

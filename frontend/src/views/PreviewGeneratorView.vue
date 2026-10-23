<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/api/client'
defineOptions({ name: 'PreviewGeneratorView' })
import { useNotification } from '@/composables'

const { notify } = useNotification()

const isLoading = ref(false)
const itemId = ref('')
const count = ref(12)
const startPct = ref(10)
const endPct = ref(90)
const pathMappings = ref<{ source: string; target: string }[]>([])
const generatedImages = ref<string[]>([])
const selectedImage = ref<string | null>(null)
const showAdvanced = ref(false)

onMounted(async () => {
  try {
    const cfg = await api.get<any>('/api/previews/config')
    count.value = cfg.count ?? 12
    startPct.value = cfg.start_pct ?? 10
    endPct.value = cfg.end_pct ?? 90
    if (cfg.path_mappings) {
      pathMappings.value = cfg.path_mappings.map((m: any) => ({
        source: m.key || m.source || '',
        target: m.value || m.target || '',
      }))
    }
  } catch (e) {
    console.error('Failed to load config', e)
  }
})

const isSavingConfig = ref(false)

async function saveConfig() {
  isSavingConfig.value = true
  try {
    await api.post('/api/previews/config', {
      count: count.value,
      start_pct: startPct.value,
      end_pct: endPct.value,
      path_mappings: pathMappings.value,
    })
    notify('保存成功', '配置已保存', 'success')
  } catch (e: any) {
    notify('保存失败', e.message || '未知错误', 'error')
  } finally {
    isSavingConfig.value = false
  }
}

async function generatePreviews() {
  if (!itemId.value) {
    notify('提示', '请输入项目ID', 'warning')
    return
  }

  await saveConfig()

  isLoading.value = true
  generatedImages.value = []
  selectedImage.value = null

  try {
    const data = await api.post<any>('/api/previews/generate', {
      item_id: itemId.value,
      count: count.value,
      start_pct: startPct.value,
      end_pct: endPct.value,
      path_mappings: pathMappings.value,
    })

    if (data.success) {
      generatedImages.value = data.images
      notify('生成成功', '', 'success')
    } else {
      notify('生成失败', data.message, 'error')
    }
  } catch (error: any) {
    notify('请求出错', error.message, 'error')
  } finally {
    isLoading.value = false
  }
}

function selectImage(img: string) {
  selectedImage.value = img
}

async function uploadImage() {
  if (!selectedImage.value) return

  isLoading.value = true
  try {
    const data = await api.post<any>('/api/previews/upload', {
      item_id: itemId.value,
      image_url: selectedImage.value,
    })

    if (data.success) {
      notify('上传成功', '设为封面完毕', 'success')
    } else {
      notify('上传失败', data.message, 'error')
    }
  } catch (error: any) {
    notify('请求出错', error.message, 'error')
  } finally {
    isLoading.value = false
  }
}

function addPathMapping() {
  pathMappings.value.push({ source: '', target: '' })
}

function removePathMapping(index: number) {
  pathMappings.value.splice(index, 1)
}
</script>

<template>
  <v-container fluid class="pa-6">
    <div class="d-flex flex-wrap align-center mb-6 ga-3">
      <div class="flex-grow-1">
        <h1 class="text-h5 font-weight-bold">封面预览截图生成</h1>
        <p class="text-caption text-medium-emphasis mt-1">为 Emby 中的剧集/视频生成预览截图并设为封面</p>
      </div>
    </div>

    <!-- 配置卡片 -->
    <v-card variant="outlined" rounded="xl" class="mb-4">
      <v-card-text>
        <div class="control-row">
          <v-text-field v-model="itemId" label="Emby ID" density="compact" variant="outlined" placeholder="输入视频/剧集 ID" class="miw-160px flex-1" />
          <v-text-field v-model.number="count" label="截图数量" type="number" min="1" max="50" density="compact" variant="outlined" class="mw-120px" />
          <v-text-field v-model.number="startPct" label="开始%" type="number" min="0" max="99" density="compact" variant="outlined" class="mw-110px" />
          <v-text-field v-model.number="endPct" label="结束%" type="number" min="1" max="100" density="compact" variant="outlined" class="mw-110px" />
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-play" :loading="isLoading" :disabled="isLoading || !itemId" @click="generatePreviews">
            开始生成
          </v-btn>
        </div>

        <!-- 高级设置 -->
        <v-btn variant="text" size="small" :append-icon="showAdvanced ? 'mdi-chevron-up' : 'mdi-chevron-down'" @click="showAdvanced = !showAdvanced">
          高级设置：路径映射
        </v-btn>

        <v-expand-transition>
          <div v-if="showAdvanced" class="mt-3">
            <v-alert type="info" variant="tonal" density="compact" class="mb-3">
              如果 Emby 返回的路径在当前容器中无法访问（例如 CloudDrive 挂载路径差异），请在此配置映射规则。
            </v-alert>

            <div v-for="(mapping, index) in pathMappings" :key="index" class="d-flex ga-2 mb-2">
              <v-text-field v-model="mapping.source" label="源路径" density="compact" variant="outlined" placeholder="/medata/CloudDrive/123云盘/" />
              <v-text-field v-model="mapping.target" label="目标路径" density="compact" variant="outlined" placeholder="http://192.168.50.12:19798/static/..." />
              <v-btn icon="mdi-delete" variant="text" size="small" color="error" @click="removePathMapping(index)" />
            </div>
            <div class="d-flex ga-2">
              <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-plus" @click="addPathMapping">添加映射</v-btn>
              <v-spacer />
              <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-content-save" :loading="isSavingConfig" @click="saveConfig">保存配置</v-btn>
            </div>
          </div>
        </v-expand-transition>
      </v-card-text>
    </v-card>

    <!-- 预览结果 -->
    <v-card v-if="generatedImages.length > 0" variant="outlined" rounded="xl">
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-image-multiple-outline" class="mr-2" />
        预览结果
        <v-spacer />
        <v-btn color="success" variant="tonal" size="small" :disabled="!selectedImage || isLoading" @click="uploadImage" prepend-icon="mdi-check">
          设为封面
        </v-btn>
      </v-card-title>
      <v-divider />

      <v-card-text>
        <v-row density="compact">
          <v-col v-for="(img, index) in generatedImages" :key="index" cols="6" sm="4" md="3" lg="2">
            <div
              class="thumb-select-wrapper cursor-pointer"
              :class="{ 'thumb-select--selected': selectedImage === img }"
              @click="selectImage(img)"
            >
              <v-img :src="img" aspect-ratio="16/9" contain />
              <!-- 选中勾 -->
              <transition name="fade-check">
                <div v-if="selectedImage === img" class="thumb-select-check">
                  <v-icon size="18" icon="mdi-check-circle" />
                </div>
              </transition>
            </div>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- 加载中 -->
    <div v-if="isLoading && generatedImages.length === 0" class="text-center pa-8">
      <v-progress-circular indeterminate color="primary" size="48" />
      <p class="mt-3 text-medium-emphasis">正在生成预览截图...</p>
    </div>
  </v-container>
</template>

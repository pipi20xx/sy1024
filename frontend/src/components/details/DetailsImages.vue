<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDetailsStore } from '@/stores'
import { useNotification, useConfirm } from '@/composables'

const store = useDetailsStore()
const { notify } = useNotification()
const { confirm } = useConfirm()

const images = computed(() => store.itemDetails?.images || [])
const webImages = computed(() => store.webImages)

// 网络下载 — 步骤式交互
const showWebDialog = ref(false)
const webStep = ref<'config' | 'browse'>('config')

// 选择配置
const webSources = ref<string[]>(['tmdb', 'fanart'])
const webImageTypes = ref<string[]>(['poster', 'fanart', 'logo'])

const sourceOptions = [
  { title: 'TMDb', value: 'tmdb' },
  { title: 'Fanart', value: 'fanart' },
]
const imageTypeOptions = [
  { title: '海报', value: 'poster' },
  { title: '背景', value: 'fanart' },
  { title: 'Logo', value: 'logo' },
  { title: '艺术图', value: 'clearart' },
  { title: '缩略图', value: 'thumb' },
  { title: '横幅', value: 'banner' },
  { title: '光盘', value: 'disc' },
]

// 选中图片索引
const selectedWebImages = ref<number[]>([])

function isWebImageSelected(index: number) {
  return selectedWebImages.value.includes(index)
}

function toggleWebImage(index: number) {
  const idx = selectedWebImages.value.indexOf(index)
  if (idx >= 0) selectedWebImages.value.splice(idx, 1)
  else selectedWebImages.value.push(index)
}

const selectedWebImagesCount = computed(() => selectedWebImages.value.length)

// 按分类分组网络图片
const webImagesByType = computed(() => {
  const groups: Record<string, { label: string; images: { img: any; index: number }[] }> = {}
  webImages.value.forEach((img: any, i: number) => {
    const type = img.type || img.label || 'other'
    if (!groups[type]) {
      const opt = imageTypeOptions.find(o => o.value === type)
      groups[type] = { label: opt ? opt.title : type, images: [] }
    }
    groups[type].images.push({ img, index: i })
  })
  return groups
})

// 分类选择/取消
function toggleSelectType(type: string) {
  const group = webImagesByType.value[type]
  if (!group) return
  const allSelected = group.images.every(e => selectedWebImages.value.includes(e.index))
  if (allSelected) {
    // 取消该分类全选
    selectedWebImages.value = selectedWebImages.value.filter(idx => !group.images.some(e => e.index === idx))
  } else {
    // 全选该分类
    group.images.forEach(e => {
      if (!selectedWebImages.value.includes(e.index)) selectedWebImages.value.push(e.index)
    })
  }
}

function isTypeFullySelected(type: string) {
  const group = webImagesByType.value[type]
  if (!group || group.images.length === 0) return false
  return group.images.every(e => selectedWebImages.value.includes(e.index))
}

// 打开配置
function handleOpenWebConfig() {
  webStep.value = 'config'
  selectedWebImages.value = []
  showWebDialog.value = true
}

// 加载网络图片
async function handleFetchWebImages() {
  if (webSources.value.length === 0) { notify('提示', '请选择至少一个来源', 'warning'); return }
  if (webImageTypes.value.length === 0) { notify('提示', '请选择至少一种图片类型', 'warning'); return }
  await store.loadWebImages(webImageTypes.value, webSources.value)
  webStep.value = 'browse'
}

// 保存选中
async function handleSaveWebImages() {
  const selected = webImages.value
    .filter((_: any, i: number) => selectedWebImages.value.includes(i))
    .map((img: any) => ({ url: img.full_url || img.preview_url, label: img.label || img.type || '' }))

  if (selected.length === 0) { notify('提示', '请选择图片', 'warning'); return }

  const success = await store.saveSelectedWebImages(selected, 'overwrite')
  if (success) {
    notify('图片保存成功', '', 'success')
    selectedWebImages.value = []
    showWebDialog.value = false
  } else {
    notify('保存失败', '', 'error')
  }
}

// 全选/取消
function handleSelectAll() {
  if (selectedWebImages.value.length === webImages.value.length) {
    selectedWebImages.value = []
  } else {
    selectedWebImages.value = webImages.value.map((_: any, i: number) => i)
  }
}

/** 判断图片是否为横向（16:9），否则为竖向海报（2:3） */
function isLandscapeImage(image: any) {
  const type = (image.type || '').toLowerCase()
  const name = (image.name || '').toLowerCase()
  const label = (image.label || '').toLowerCase()
  const combined = `${type} ${name} ${label}`
  return combined.includes('backdrop') || combined.includes('fanart') || combined.includes('背景') ||
    combined.includes('logo') || combined.includes('disc') || combined.includes('光盘') ||
    combined.includes('thumb') || combined.includes('缩略图') || combined.includes('landscape') ||
    combined.includes('banner') || combined.includes('横幅') || combined.includes('clearart') ||
    combined.includes('艺术图')
}

/** 判断图片是否为透明背景类型（logo / clearart / disc），需要棋盘格背景 */
function isTransparentImage(image: any) {
  const type = (image.type || '').toLowerCase()
  const name = (image.name || '').toLowerCase()
  const label = (image.label || '').toLowerCase()
  const combined = `${type} ${name} ${label}`
  return combined.includes('logo') || combined.includes('clearart') || combined.includes('艺术图') ||
    combined.includes('disc') || combined.includes('光盘')
}

async function handleDownloadFromEmby() {
  const success = await store.downloadFromEmby()
  if (success) notify('从 Emby 下载图片成功', '', 'success')
  else notify('下载失败', '', 'error')
}

async function handleDeleteAllImages() {
  const ok = await confirm({
    title: '删除所有图片',
    content: '将删除 Override 目录下的所有本地图片文件。此操作不可恢复！',
    confirmColor: 'error',
  })
  if (!ok) return
  const success = await store.deleteImages()
  if (success) notify('图片已删除', '', 'success')
  else notify('删除失败', '', 'error')
}

// ═══ Emby 视频截图 ═══
const showScreenshotDialog = ref(false)
const selectedScreenshot = ref<string | null>(null)
const screenshotSaveType = ref('poster')
const screenshotTypeOptions = [
  { title: '海报 (Poster)', value: 'poster' },
  { title: '背景 (Fanart)', value: 'fanart' },
  { title: '缩略图 (Thumb)', value: 'thumb' },
]

// 剧集截图：季/集选择
const isTv = computed(() => store.currentItemType === 'tmdb-tv')
const screenshotSeason = ref<number | null>(null)
const screenshotEpisode = ref<number | null>(null)

// 从 store 的 seasons 数据构建可选季列表
// 剧集组视图下 season_number 即为剧集组编号，直接用
const screenshotSeasons = computed(() => {
  if (!isTv.value || !store.itemDetails?.seasons) return []
  return store.itemDetails.seasons.map(s => ({
    title: `第 ${s.season_number} 季${s.metadata?.name ? ' - ' + s.metadata.name : ''}`,
    value: s.season_number,
    episodes: s.episodes || [],
  }))
})

// 当前选中季的集列表
// 剧集组视图用 custom 编号，标准视图用原始编号，不回退
const screenshotEpisodes = computed(() => {
  if (screenshotSeason.value === null) return []
  const seasonData = screenshotSeasons.value.find(s => s.value === screenshotSeason.value)
  if (!seasonData) return []
  return seasonData.episodes.map((ep: any) => {
    const num = store.currentViewMode === 'episodegroup'
      ? ep.custom_episode_number
      : ep.episode_number
    return {
      title: `第 ${num} 集${ep.metadata?.name ? ' - ' + ep.metadata.name : ''}`,
      value: num,
    }
  })
})

// 季变化时重置集号
watch(screenshotSeason, () => {
  if (screenshotEpisodes.value.length > 0) {
    screenshotEpisode.value = screenshotEpisodes.value[0].value
  } else {
    screenshotEpisode.value = null
  }
})

function handleOpenScreenshot() {
  selectedScreenshot.value = null
  screenshotSeason.value = null
  screenshotEpisode.value = null
  if (isTv.value && screenshotSeasons.value.length > 0) {
    screenshotSeason.value = screenshotSeasons.value[0].value
  }
  showScreenshotDialog.value = true
}

async function handleGenerateScreenshots() {
  if (isTv.value) {
    if (screenshotSeason.value === null || screenshotEpisode.value === null) {
      notify('提示', '请选择季和集', 'warning')
      return
    }
    const result = await store.generatePreviews(screenshotSeason.value, screenshotEpisode.value)
    if (!result.success) {
      notify('截图失败', result.message, 'error')
    }
  } else {
    const result = await store.generatePreviews()
    if (!result.success) {
      notify('截图失败', result.message, 'error')
    }
  }
}

function selectScreenshot(img: string) {
  selectedScreenshot.value = img
}

async function handleSaveScreenshot() {
  if (!selectedScreenshot.value) return
  let success: boolean
  if (isTv.value && screenshotSeason.value !== null && screenshotEpisode.value !== null) {
    success = await store.savePreviewImage(
      selectedScreenshot.value,
      screenshotSaveType.value,
      screenshotSeason.value,
      screenshotEpisode.value,
    )
  } else {
    success = await store.savePreviewImage(selectedScreenshot.value, screenshotSaveType.value)
  }
  if (success) {
    notify('保存成功', '', 'success')
    selectedScreenshot.value = null
    showScreenshotDialog.value = false
    store.clearPreviews()
  } else {
    notify('保存失败', '', 'error')
  }
}
</script>

<template>
  <v-container fluid>
    <div class="d-flex flex-wrap ga-2 mb-4">
      <v-btn size="small" variant="tonal" color="primary" @click="handleOpenWebConfig" prepend-icon="mdi-web">从网络下载</v-btn>
      <v-btn size="small" variant="tonal" color="success" @click="handleDownloadFromEmby" :loading="store.isImagesLoading" prepend-icon="mdi-cloud-download">从 Emby 下载</v-btn>
      <v-btn size="small" variant="tonal" color="info" @click="handleOpenScreenshot" prepend-icon="mdi-video-image">视频截图</v-btn>
      <v-spacer />
      <v-btn size="small" variant="tonal" color="error" @click="handleDeleteAllImages" prepend-icon="mdi-delete">删除所有</v-btn>
    </div>

    <v-sheet v-if="images.length" class="pa-4" rounded border>
      <div class="text-subtitle-2 font-weight-bold mb-3">本地图片 ({{ images.length }})</div>
      <v-row>
        <v-col v-for="(img, i) in images" :key="i" :cols="isLandscapeImage(img) ? 12 : 6" :sm="isLandscapeImage(img) ? 6 : 4" :md="isLandscapeImage(img) ? 4 : 3">
          <v-card variant="outlined" class="image-card">
            <div class="image-card__poster">
              <v-img :src="img.url" :alt="img.label || img.name" :aspect-ratio="isLandscapeImage(img) ? 16/9 : 2/3" :cover="!isLandscapeImage(img)" :contain="isLandscapeImage(img)" :class="{ 'logo-image-bg': isTransparentImage(img) }" class="image-card__img">
                <template #error>
                  <v-sheet class="d-flex align-center justify-center fill-height"><v-icon>mdi-image-off</v-icon></v-sheet>
                </template>
              </v-img>
            </div>
            <v-card-text class="pa-2 text-center text-caption text-truncate">{{ img.label || img.name }}</v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </v-sheet>

    <v-alert v-else type="info" variant="tonal" class="text-center">
      <v-icon size="48" class="mb-2">mdi-image-off-outline</v-icon>
      <div>暂无本地图片</div>
    </v-alert>

    <!-- 网络下载对话框 -->
    <v-dialog v-model="showWebDialog" max-width="900" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-web" class="mr-2" />
          从网络下载图片
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showWebDialog = false" />
        </v-card-title>
        <v-divider />

        <!-- 步骤 1: 选择配置 -->
        <v-card-text v-if="webStep === 'config'">
          <div class="text-subtitle-2 font-weight-bold mb-3">
            <v-icon start size="small">mdi-filter-variant</v-icon>
            选择下载来源和图片类型
          </div>

          <div class="mb-4">
            <div class="text-caption text-medium-emphasis mb-1">来源</div>
            <div class="d-flex ga-3">
              <v-checkbox v-for="s in sourceOptions" :key="s.value" v-model="webSources" :value="s.value" :label="s.title" density="compact" hide-details />
            </div>
          </div>

          <div class="mb-4">
            <div class="text-caption text-medium-emphasis mb-1">图片类型</div>
            <div class="d-flex flex-wrap ga-3">
              <v-checkbox v-for="t in imageTypeOptions" :key="t.value" v-model="webImageTypes" :value="t.value" :label="t.title" density="compact" hide-details />
            </div>
          </div>
        </v-card-text>

        <!-- 步骤 2: 浏览并选择图片 -->
        <v-card-text v-else>
          <div v-if="store.isImagesLoading" class="text-center pa-8">
            <v-progress-circular indeterminate color="primary" />
            <p class="mt-2 text-medium-emphasis">正在搜索图片...</p>
          </div>

          <template v-else-if="webImages.length">
            <!-- 顶栏：分类选择提示 + 全选 -->
            <div class="d-flex align-center mb-3">
              <span class="text-subtitle-2 font-weight-bold">搜索结果 ({{ webImages.length }})</span>
              <v-spacer />
              <v-btn size="x-small" variant="tonal" @click="handleSelectAll">
                {{ selectedWebImagesCount === webImages.length ? '取消全选' : '全选' }}
              </v-btn>
            </div>

            <!-- 按类型分组展示 -->
            <div v-for="(group, type) in webImagesByType" :key="type" class="mb-4">
              <div class="d-flex align-center mb-2">
                <v-btn size="x-small" :variant="isTypeFullySelected(type) ? 'flat' : 'tonal'" :color="isTypeFullySelected(type) ? 'primary' : 'default'" @click="toggleSelectType(type)" density="comfortable">
                  <v-icon start size="small">{{ isTypeFullySelected(type) ? 'mdi-check-circle' : 'mdi-circle-outline' }}</v-icon>
                  {{ group.label }}
                </v-btn>
                <span class="text-caption text-medium-emphasis ml-2">{{ group.images.length }} 张</span>
              </div>
              <v-row>
                <v-col v-for="{ img, index } in group.images" :key="index" :cols="isLandscapeImage(img) ? 12 : 6" :sm="isLandscapeImage(img) ? 6 : 4" :md="isLandscapeImage(img) ? 4 : 3">
                  <v-card variant="outlined" :color="isWebImageSelected(index) ? 'primary' : undefined" class="cursor-pointer image-card" @click="toggleWebImage(index)">
                    <div class="image-card__poster">
                      <v-img :src="img.preview_url || img.full_url" :aspect-ratio="isLandscapeImage(img) ? 16/9 : 2/3" :cover="!isLandscapeImage(img)" :contain="isLandscapeImage(img)" :class="{ 'logo-image-bg': isTransparentImage(img) }" class="image-card__img">
                        <template #error><v-sheet class="d-flex align-center justify-center fill-height"><v-icon>mdi-image-off</v-icon></v-sheet></template>
                      </v-img>
                    </div>
                    <v-card-text class="pa-2 text-center text-caption text-truncate">{{ img.source }}</v-card-text>
                    <v-overlay :model-value="isWebImageSelected(index)" contained persistent class="align-center justify-center">
                      <v-icon size="40" color="primary">mdi-check-circle</v-icon>
                    </v-overlay>
                  </v-card>
                </v-col>
              </v-row>
            </div>
          </template>

          <v-alert v-else type="info" variant="tonal" class="text-center">
            <v-icon size="48" class="mb-2">mdi-image-off-outline</v-icon>
            <div>未找到符合条件的图片</div>
          </v-alert>
        </v-card-text>

        <v-divider />
        <v-card-actions>
          <span v-if="webStep === 'browse'" class="text-caption text-medium-emphasis">已选 {{ selectedWebImagesCount }} 张</span>
          <v-spacer />
          <v-btn v-if="webStep === 'browse'" variant="tonal" color="grey" prepend-icon="mdi-arrow-left" @click="webStep = 'config'">返回筛选</v-btn>
          <v-btn v-if="webStep === 'config'" variant="tonal" color="grey" prepend-icon="mdi-close" @click="showWebDialog = false">取消</v-btn>
          <v-btn v-if="webStep === 'config'" color="primary" variant="tonal" prepend-icon="mdi-magnify" @click="handleFetchWebImages" :loading="store.isImagesLoading">搜索图片</v-btn>
          <v-btn v-if="webStep === 'browse'" color="primary" variant="tonal" prepend-icon="mdi-content-save" :disabled="selectedWebImagesCount === 0" @click="handleSaveWebImages">保存选中 ({{ selectedWebImagesCount }})</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 视频截对话框 -->
    <v-dialog v-model="showScreenshotDialog" :max-width="store.previewImages.length ? 1100 : 600" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-video-image" class="mr-2" />
          Emby 视频截图
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showScreenshotDialog = false; store.clearPreviews()" />
        </v-card-title>
        <v-divider />

        <v-card-text>
          <!-- 加载中 -->
          <div v-if="store.isPreviewLoading" class="text-center pa-8">
            <v-progress-circular indeterminate color="info" size="48" />
            <p class="mt-3 text-medium-emphasis">正在从视频文件截取画面...</p>
          </div>

          <!-- 截图结果 -->
          <template v-else-if="store.previewImages.length">
            <div class="d-flex align-center mb-3 ga-2 flex-wrap">
              <span class="text-subtitle-2 font-weight-bold">截图结果 ({{ store.previewImages.length }})</span>
              <v-spacer />
              <!-- 电影模式才显示保存类型选择，剧集模式固定为集缩略图 -->
              <v-select v-if="!isTv" v-model="screenshotSaveType" :items="screenshotTypeOptions" item-title="title" item-value="value" density="compact" hide-details variant="outlined" class="mw-200px" />
              <v-btn color="success" variant="tonal" size="small" :disabled="!selectedScreenshot" @click="handleSaveScreenshot" prepend-icon="mdi-content-save">
                保存到 Override
              </v-btn>
            </div>

            <v-row density="compact">
              <v-col v-for="(img, index) in store.previewImages" :key="index" cols="6" sm="4" md="3">
                <div
                  class="thumb-select-wrapper cursor-pointer"
                  :class="{ 'thumb-select--selected': selectedScreenshot === img }"
                  @click="selectScreenshot(img)"
                >
                  <v-img :src="img" aspect-ratio="16/9" contain />
                  <transition name="fade-check">
                    <div v-if="selectedScreenshot === img" class="thumb-select-check">
                      <v-icon size="18" icon="mdi-check-circle" />
                    </div>
                  </transition>
                </div>
              </v-col>
            </v-row>
          </template>

          <!-- 空状态 -->
          <div v-else class="text-center pa-6">
            <v-icon size="48" color="grey-lighten-1" class="mb-2">mdi-video-image</v-icon>
            <p class="text-medium-emphasis mb-4">从 Emby 视频文件截取画面，可保存为集缩略图</p>
            
            <!-- 剧集：季/集选择 -->
            <div v-if="isTv" class="d-flex flex-column align-center ga-3 mb-4">
              <v-select
                v-model="screenshotSeason"
                :items="screenshotSeasons"
                item-title="title"
                item-value="value"
                label="选择季"
                density="compact"
                variant="outlined"
                hide-details
                class="w-100 mw-360px"
              />
              <v-select
                v-model="screenshotEpisode"
                :items="screenshotEpisodes"
                item-title="title"
                item-value="value"
                label="选择集"
                density="compact"
                variant="outlined"
                hide-details
                :disabled="!screenshotSeason"
                class="w-100 mw-360px"
              />
            </div>

            <v-btn color="info" variant="tonal" prepend-icon="mdi-play" @click="handleGenerateScreenshots"
              :disabled="isTv && (screenshotSeason === null || screenshotEpisode === null)"
            >开始截图</v-btn>
          </div>
        </v-card-text>
      </v-card>
    </v-dialog>
  </v-container>
</template>

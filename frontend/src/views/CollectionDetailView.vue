<script setup lang="ts">
import { ref, watch, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
defineOptions({ name: 'CollectionDetailView' })
import { useCollectionStore } from '@/stores'
import { getCollectionDetails, uploadCollectionImage } from '@/api/collections'
import { useNotification, useConfirm } from '@/composables'
import type { Collection, ItemType } from '@/types'
import ItemPickerDialog, { type SelectedItem } from '@/components/collections/ItemPickerDialog.vue'
import CollectionPosterDialog from '@/components/collections/CollectionPosterDialog.vue'

const route = useRoute()
const router = useRouter()
const store = useCollectionStore()
const { notify } = useNotification()
const { confirm } = useConfirm()

const isNew = computed(() => route.params.filename === '__new__')

// ── 状态 ──
const isLoading = ref(false)
const isEditing = ref(false)
const collectionData = ref<Collection | null>(null)
const activeTab = ref('basic')
const imageUpdateTrigger = ref(0)
const fileInput = ref<HTMLInputElement | null>(null)
const uploadType = ref<'poster' | 'backdrop' | 'logo'>('poster')

// 编辑表单
const formData = ref<{
  name: string
  overview: string
  movies: { id: string; name: string }[]
  series: { id: string; name: string }[]
}>({ name: '', overview: '', movies: [], series: [] })

// 添加项目的输入
const addId = ref('')
const addName = ref('')
const addType = ref<ItemType>('tmdb-tv')

// ── 选择器弹框 ──
const showItemPicker = ref(false)
const showPosterGenerator = ref(false)

// ── 初始化 ──
onMounted(async () => {
  if (isNew.value) {
    isEditing.value = true
    formData.value = { name: '', overview: '', movies: [], series: [] }
  } else {
    await loadDetails()
  }
})

async function loadDetails() {
  const filename = route.params.filename as string
  if (!filename || filename === '__new__') return
  isLoading.value = true
  try {
    const details = await getCollectionDetails(filename)
    collectionData.value = details
    formData.value = {
      name: details.collection_name || details.name || '',
      overview: details.overview || '',
      movies: details.movies || [],
      series: details.series || [],
    }
  } catch (e: any) {
    notify('加载失败', e.message, 'error')
  } finally {
    isLoading.value = false
  }
}

// ── 操作 ──
async function handleSave() {
  if (!formData.value.name.trim()) {
    notify('提示', '请输入合集名称', 'warning')
    return
  }
  const data = {
    name: formData.value.name,
    overview: formData.value.overview,
    movies: formData.value.movies,
    series: formData.value.series,
  }
  try {
    if (isNew.value) {
      await store.create(data)
      notify('创建成功', '', 'success')
      // 创建成功后跳转回列表
      router.replace({ name: 'collections' })
    } else {
      const filename = route.params.filename as string
      await store.update(filename, data)
      notify('保存成功', '', 'success')
      isEditing.value = false
      imageUpdateTrigger.value++
      await loadDetails()
    }
  } catch (e: any) {
    notify('保存失败', e.message, 'error')
  }
}

function handleCancelEdit() {
  isEditing.value = false
  // 还原表单数据
  if (collectionData.value) {
    formData.value = {
      name: collectionData.value.collection_name || collectionData.value.name || '',
      overview: collectionData.value.overview || '',
      movies: [...(collectionData.value.movies || [])],
      series: [...(collectionData.value.series || [])],
    }
  }
}

const isSyncing = ref(false)
const syncProgress = ref('')

async function handleSync() {
  const filename = route.params.filename as string
  isSyncing.value = true
  syncProgress.value = ''
  try {
    await store.syncToEmby(filename, (msg: string) => {
      syncProgress.value = msg
    })
    notify('同步成功', '', 'success')
  } catch (e: any) {
    notify('同步失败', e.message, 'error')
  } finally {
    isSyncing.value = false
    syncProgress.value = ''
  }
}

async function handleDelete() {
  if (!collectionData.value) return
  const ok = await confirm({
    title: '删除合集',
    content: `确认删除合集「${collectionData.value.collection_name || collectionData.value.name}」？此操作将删除本地的 .json 合集文件。`,
    confirmColor: 'error',
  })
  if (!ok) return
  const filename = route.params.filename as string
  const success = await store.remove(filename)
  if (success) {
    notify('已删除', '', 'success')
    router.replace({ name: 'collections' })
  }
}

function handleExport() {
  const filename = route.params.filename as string
  window.open(`/api/collections/${filename}/export_zip`, '_blank')
}

function triggerUpload(type: 'poster' | 'backdrop' | 'logo') {
  uploadType.value = type
  fileInput.value?.click()
}

async function handleFileUpload(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  const filename = route.params.filename as string
  try {
    await uploadCollectionImage(filename, uploadType.value, file)
    notify('上传成功', '', 'success')
    imageUpdateTrigger.value++
    await loadDetails()
  } catch (e: any) {
    notify('上传失败', e.message, 'error')
  }
  target.value = ''
}

// ── 条目管理 ──
function addItem() {
  if (!addId.value.trim()) return
  const item = { id: addId.value.trim(), name: addName.value.trim() || addId.value.trim() }
  if (addType.value === 'tmdb-movies2') {
    if (!formData.value.movies.find(m => m.id === item.id)) formData.value.movies.push(item)
  } else {
    if (!formData.value.series.find(s => s.id === item.id)) formData.value.series.push(item)
  }
  addId.value = ''
  addName.value = ''
}

function removeMovie(id: string) {
  formData.value.movies = formData.value.movies.filter(m => m.id !== id)
}

function removeSeries(id: string) {
  formData.value.series = formData.value.series.filter(s => s.id !== id)
}

// ── ItemPicker 回调 ──
function handleItemsSelected(items: SelectedItem[]) {
  const newMovies: { id: string; name: string }[] = []
  const newSeries: { id: string; name: string }[] = []
  items.forEach(item => {
    if (item.type === 'tmdb-movies2') {
      newMovies.push({ id: item.id, name: item.name })
    } else {
      newSeries.push({ id: item.id, name: item.name })
    }
  })
  formData.value.movies = newMovies
  formData.value.series = newSeries
}

const currentSelectedItems = computed<SelectedItem[]>(() => {
  const selected: SelectedItem[] = []
  formData.value.movies.forEach(m => selected.push({ id: m.id, name: m.name, type: 'tmdb-movies2' as ItemType }))
  formData.value.series.forEach(s => selected.push({ id: s.id, name: s.name, type: 'tmdb-tv' as ItemType }))
  return selected
})

// 海报生成用的 movie/series IDs（分开传，避免后端试错搜索）
const posterMovieIds = computed(() => formData.value.movies.map(m => m.id))
const posterSeriesIds = computed(() => formData.value.series.map(s => s.id))
const posterItemIds = computed(() => [...posterMovieIds.value, ...posterSeriesIds.value])

// 海报生成用的 titles_map（供后端统一入口启用标题优先搜索）
const posterTitlesMap = computed(() => {
  const map: Record<string, string[]> = {}
  for (const m of formData.value.movies) {
    if (m.id && m.name) map[m.id] = [m.name]
  }
  for (const s of formData.value.series) {
    if (s.id && s.name) map[s.id] = [s.name]
  }
  return Object.keys(map).length ? map : undefined
})

// ── 图片 URL ──
function getCollectionImageUrl(type: 'poster' | 'backdrop' | 'logo') {
  const filename = route.params.filename as string
  if (!filename || filename === '__new__') return ''
  const baseName = filename.replace('.json', '')
  const suffixMap: Record<string, string> = {
    poster: '_poster.jpg',
    backdrop: '_fanart.jpg',
    logo: '_logo.png',
  }
  return `/api/emby-collections/images/${baseName}${suffixMap[type]}?t=${imageUpdateTrigger.value}`
}

const posterUrl = computed(() => {
  if (collectionData.value?.poster_path) {
    return `${collectionData.value.poster_path}?t=${imageUpdateTrigger.value}`
  }
  return getCollectionImageUrl('poster')
})

// ── 页面标题 ──
const pageTitle = computed(() => {
  if (isNew.value) return '新建合集'
  return collectionData.value?.collection_name || collectionData.value?.name || '合集详情'
})
</script>

<template>
  <v-container fluid class="pa-6 page-container">
    <!-- 顶部操作栏 -->
    <div class="d-flex flex-wrap align-center mb-4 ga-2">
      <v-btn variant="tonal" color="grey" size="small" prepend-icon="mdi-arrow-left" @click="router.push({ name: 'collections' })">
        返回列表
      </v-btn>
      <h1 class="text-h6 font-weight-bold ml-2">{{ pageTitle }}</h1>
      <v-spacer />
      <template v-if="!isNew">
        <v-btn size="small" variant="tonal" color="info" prepend-icon="mdi-sync" :loading="isSyncing" :disabled="isSyncing" @click="handleSync">应用到 Emby</v-btn>
        <v-btn size="small" variant="tonal" prepend-icon="mdi-export" @click="handleExport" class="ml-2">导出数据</v-btn>
        <v-btn v-if="!isEditing" size="small" variant="tonal" color="primary" prepend-icon="mdi-pencil" @click="isEditing = true" class="ml-2">编辑</v-btn>
        <v-btn v-else size="small" variant="tonal" color="primary" prepend-icon="mdi-content-save" @click="handleSave" class="ml-2">保存</v-btn>
        <v-btn v-if="isEditing" size="small" variant="tonal" color="grey" prepend-icon="mdi-close" @click="handleCancelEdit" class="ml-2">取消</v-btn>
        <v-btn size="small" variant="tonal" color="error" prepend-icon="mdi-delete" @click="handleDelete" class="ml-2">删除</v-btn>
      </template>
      <template v-else>
        <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-plus" @click="handleSave">创建合集</v-btn>
      </template>
    </div>

    <!-- 同步进度 -->
    <v-alert v-if="isSyncing && syncProgress" type="info" variant="tonal" density="compact" class="mb-4">
      <v-progress-circular indeterminate size="16" width="2" color="primary" class="mr-2" />
      {{ syncProgress }}
    </v-alert>

    <v-divider class="mb-4" />

    <!-- 加载中 -->
    <div v-if="isLoading" class="loading-state d-flex justify-center align-center">
      <v-progress-circular indeterminate color="primary" size="48" />
    </div>

    <!-- 主体内容 -->
    <v-row v-else>
      <!-- 左侧：海报 -->
      <v-col cols="12" md="4" lg="3">
        <v-img
          v-if="posterUrl"
          :src="posterUrl"
          aspect-ratio="2/3"
          max-width="320"
          rounded="xl"
          cover
          class="mx-auto"
        >
          <template #error>
            <div class="d-flex align-center justify-center fill-height bg-surface-variant">
              <v-icon size="64" color="grey-lighten-1">mdi-image-off</v-icon>
            </div>
          </template>
        </v-img>
        <v-sheet v-else rounded="xl" class="d-flex align-center justify-center bg-surface-variant mx-auto" width="280" height="420">
          <v-icon size="64" color="grey-lighten-1">mdi-folder-image</v-icon>
        </v-sheet>

        <!-- 上传按钮 -->
        <div v-if="!isNew" class="d-flex ga-2 mt-3 justify-center flex-wrap">
          <v-btn size="small" variant="tonal" prepend-icon="mdi-image-plus" @click="triggerUpload('poster')">海报</v-btn>
          <v-btn size="small" variant="tonal" prepend-icon="mdi-image-plus" @click="triggerUpload('backdrop')">背景</v-btn>
          <v-btn size="small" variant="tonal" prepend-icon="mdi-image-plus" @click="triggerUpload('logo')">Logo</v-btn>
        </div>
        <input type="file" ref="fileInput" accept="image/*" class="d-none" @change="handleFileUpload" />
      </v-col>

      <!-- 右侧：详情内容 -->
      <v-col cols="12" md="8" lg="9">
        <v-tabs v-model="activeTab" density="compact" show-arrows>
          <v-tab value="basic">基本信息</v-tab>
          <v-tab v-if="!isNew" value="images">图片管理</v-tab>
          <v-tab v-if="!isNew" value="json">原始 JSON</v-tab>
        </v-tabs>

        <v-divider class="mb-4" />

        <v-window v-model="activeTab">
          <!-- ═══ 基本信息 ═══ -->
          <v-window-item value="basic">
            <!-- 查看模式 -->
            <template v-if="!isEditing">
              <h2 class="text-h6 font-weight-bold">{{ collectionData?.name || collectionData?.collection_name }}</h2>
              <p class="text-body-2 text-medium-emphasis mt-2 mb-4 overview-text">
                {{ collectionData?.overview || '暂无简介' }}
              </p>

              <!-- 电影列表 -->
              <div class="mb-4">
                <div class="text-subtitle-2 font-weight-bold mb-2">
                  <v-icon start size="18" color="primary">mdi-movie</v-icon>
                  包含电影 ({{ collectionData?.movies?.length || 0 }})
                </div>
                <div class="d-flex flex-wrap ga-2 mb-2">
                  <v-chip v-for="m in collectionData?.movies" :key="m.id" size="small" variant="tonal" label>
                    {{ m.name }} <span class="text-medium-emphasis ml-1">({{ m.id }})</span>
                  </v-chip>
                  <span v-if="!collectionData?.movies?.length" class="text-caption text-medium-emphasis">无</span>
                </div>
              </div>

              <v-divider class="my-3" />

              <!-- 剧集列表 -->
              <div>
                <div class="text-subtitle-2 font-weight-bold mb-2">
                  <v-icon start size="18" color="info">mdi-television</v-icon>
                  包含剧集 ({{ collectionData?.series?.length || 0 }})
                </div>
                <div class="d-flex flex-wrap ga-2">
                  <v-chip v-for="s in collectionData?.series" :key="s.id" size="small" variant="tonal" color="info" label>
                    {{ s.name }} <span class="text-medium-emphasis ml-1">({{ s.id }})</span>
                  </v-chip>
                  <span v-if="!collectionData?.series?.length" class="text-caption text-medium-emphasis">无</span>
                </div>
              </div>
            </template>

            <!-- 编辑模式 -->
            <template v-else>
              <v-text-field v-model="formData.name" label="合集名称 *" density="compact" variant="outlined" class="mb-3" />
              <v-textarea v-model="formData.overview" label="简介" density="compact" variant="outlined" rows="3" auto-grow class="mb-3" />

              <!-- 条目管理 -->
              <div class="text-subtitle-2 font-weight-bold mb-2">
                包含项目 (电影 {{ formData.movies.length }} / 剧集 {{ formData.series.length }})
              </div>

              <!-- 从库中选择 -->
              <div class="d-flex ga-2 mb-3">
                <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-selection" @click="showItemPicker = true">
                  从库中选择 ({{ formData.movies.length + formData.series.length }})
                </v-btn>
              </div>

              <!-- 手动添加 ID（备选） -->
              <v-expansion-panels class="mb-3">
                <v-expansion-panel>
                  <v-expansion-panel-title class="text-caption">
                    <v-icon start size="14">mdi-keyboard</v-icon>
                    手动输入 TMDB ID
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <div class="d-flex ga-2 align-center">
                      <v-select v-model="addType" :items="[
                        { title: '剧集', value: 'tmdb-tv' },
                        { title: '电影', value: 'tmdb-movies2' },
                      ]" density="compact" variant="outlined" max-width="100" hide-details />
                      <v-text-field v-model="addId" label="TMDB ID" density="compact" variant="outlined" max-width="140" @keyup.enter="addItem" />
                      <v-text-field v-model="addName" label="名称（可选）" density="compact" variant="outlined" class="flex-grow-1" @keyup.enter="addItem" />
                      <v-btn size="small" variant="tonal" @click="addItem" icon="mdi-plus" />
                    </div>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>

              <!-- 电影列表 -->
              <div v-if="formData.movies.length" class="mb-3">
                <div class="text-caption text-medium-emphasis mb-1">
                  <v-icon start size="14">mdi-movie</v-icon>电影:
                </div>
                <div class="d-flex flex-wrap ga-2">
                  <v-chip v-for="m in formData.movies" :key="m.id" size="small" variant="tonal" closable
                    @click:close="removeMovie(m.id)">
                    {{ m.name }}
                  </v-chip>
                </div>
              </div>

              <!-- 剧集列表 -->
              <div v-if="formData.series.length">
                <div class="text-caption text-medium-emphasis mb-1">
                  <v-icon start size="14">mdi-television</v-icon>剧集:
                </div>
                <div class="d-flex flex-wrap ga-2">
                  <v-chip v-for="s in formData.series" :key="s.id" size="small" variant="tonal" color="info" closable
                    @click:close="removeSeries(s.id)">
                    {{ s.name }}
                  </v-chip>
                </div>
              </div>

              <v-alert v-if="!formData.movies.length && !formData.series.length" type="info" variant="tonal" density="compact" class="mt-3">
                暂无条目，请在上方添加 TMDB ID
              </v-alert>
            </template>
          </v-window-item>

          <!-- ═══ 图片管理 ═══ -->
          <v-window-item value="images">
            <v-row>
              <v-col cols="12" md="4">
                <div class="text-subtitle-2 font-weight-bold mb-2">
                  <v-icon start size="18">mdi-image</v-icon>
                  海报 (Poster)
                </div>
                <v-img :src="getCollectionImageUrl('poster')" aspect-ratio="2/3" rounded="xl" cover>
                  <template #error>
                    <div class="d-flex align-center justify-center fill-height bg-surface-variant">
                      <v-icon color="grey-lighten-1">mdi-image-off</v-icon>
                    </div>
                  </template>
                </v-img>
                <v-btn block size="small" variant="tonal" prepend-icon="mdi-upload" class="mt-2" @click="triggerUpload('poster')">上传海报</v-btn>
                <v-btn block size="small" variant="tonal" color="primary" class="mt-2" prepend-icon="mdi-image-edit" @click="showPosterGenerator = true">生成海报</v-btn>
              </v-col>
              <v-col cols="12" md="4">
                <div class="text-subtitle-2 font-weight-bold mb-2">
                  <v-icon start size="18">mdi-image-area</v-icon>
                  背景 (Backdrop)
                </div>
                <v-img :src="getCollectionImageUrl('backdrop')" aspect-ratio="16/9" rounded="xl" cover>
                  <template #error>
                    <div class="d-flex align-center justify-center fill-height bg-surface-variant">
                      <v-icon color="grey-lighten-1">mdi-image-off</v-icon>
                    </div>
                  </template>
                </v-img>
                <v-btn block size="small" variant="tonal" prepend-icon="mdi-upload" class="mt-2" @click="triggerUpload('backdrop')">上传背景</v-btn>
              </v-col>
              <v-col cols="12" md="4">
                <div class="text-subtitle-2 font-weight-bold mb-2">
                  <v-icon start size="18">mdi-alpha-l-box</v-icon>
                  Logo
                </div>
                <v-img :src="getCollectionImageUrl('logo')" aspect-ratio="16/9" rounded="xl" contain class="logo-image-bg">
                  <template #error>
                    <div class="d-flex align-center justify-center fill-height logo-image-bg">
                      <v-icon color="grey-lighten-1">mdi-image-off</v-icon>
                    </div>
                  </template>
                </v-img>
                <v-btn block size="small" variant="tonal" prepend-icon="mdi-upload" class="mt-2" @click="triggerUpload('logo')">上传 Logo</v-btn>
              </v-col>
            </v-row>
          </v-window-item>

          <!-- ═══ 原始 JSON ═══ -->
<v-window-item value="json">
<v-card variant="outlined" rounded="xl" class="pa-4">
<pre class="text-caption json-viewer json-text">{{ JSON.stringify(collectionData, null, 2) }}</pre>
</v-card>
</v-window-item>
        </v-window>
      </v-col>
    </v-row>

    <!-- 选择媒体项目弹框 -->
    <ItemPickerDialog
      v-model="showItemPicker"
      :initial-selected-items="currentSelectedItems"
      @confirm="handleItemsSelected"
    />

    <!-- 海报生成器弹框 -->
    <CollectionPosterDialog
      v-model="showPosterGenerator"
      :collection-id="route.params.filename as string"
      :item-ids="posterItemIds"
      :movie-ids="posterMovieIds"
      :series-ids="posterSeriesIds"
      :titles-map="posterTitlesMap"
      :initial-title-zh="formData.name"
      :initial-title-en="formData.name"
      @saved="loadDetails"
    />
  </v-container>
</template>

<style scoped>
/* 简介行高 */
.overview-text {
  line-height: 1.8;
}

/* JSON 查看行高 */
.json-text {
  line-height: 1.6;
}
</style>

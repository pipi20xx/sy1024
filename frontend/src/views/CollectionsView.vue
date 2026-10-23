<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
defineOptions({ name: 'CollectionsView' })
import { useCollectionStore, useUiStore } from '@/stores'
import { useNotification } from '@/composables'
import { importCollectionZip } from '@/api/collections'
import EmbyImportDialog from '@/components/collections/EmbyImportDialog.vue'
import EmbyApplyAllDialog from '@/components/collections/EmbyApplyAllDialog.vue'
import BatchPosterDialog from '@/components/collections/BatchPosterDialog.vue'

const store = useCollectionStore()
const uiStore = useUiStore()
const { notify } = useNotification()
const router = useRouter()

const searchTerm = ref('')
const showEmbyImport = ref(false)
const showEmbyApplyAll = ref(false)
const showBatchPoster = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

onMounted(() => { store.loadCollections() })

const filteredCollections = computed(() => {
  if (!searchTerm.value) return store.collections
  const term = searchTerm.value.toLowerCase()
  return store.collections.filter((col: any) =>
    col.name.toLowerCase().includes(term) ||
    (col.overview && col.overview.toLowerCase().includes(term))
  )
})

function openDetail(col: { filename: string }) {
  router.push({ name: 'collectionDetail', params: { filename: col.filename } })
}

function openNew() {
  router.push({ name: 'collectionDetail', params: { filename: '__new__' } })
}

async function handleScan() {
  await store.scanLibrary()
  notify('扫描完成', '', 'success')
}

function triggerImport() {
  fileInput.value?.click()
}

async function handleImport(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files?.length) return
  const files = Array.from(target.files)
  let successCount = 0
  let failCount = 0
  for (const file of files) {
    try {
      const result = await importCollectionZip(file)
      if (result.success) successCount++
      else failCount++
    } catch {
      failCount++
    }
  }
  if (failCount === 0) notify(`成功导入 ${successCount} 个合集`, '', 'success')
  else notify(`导入完成: ${successCount} 成功, ${failCount} 失败`, '', 'warning')
  store.loadCollections()
  target.value = ''
}
</script>

<template>
  <v-container fluid class="pa-6">
    <!-- 页头 -->
    <div class="d-flex flex-wrap align-center mb-6 ga-3">
      <div class="flex-grow-1">
        <h1 class="text-h5 font-weight-bold">合集管理</h1>
        <p class="text-caption text-medium-emphasis mt-1">
          管理影视合集，可同步至 Emby 媒体服务器 · 共 {{ filteredCollections.length }} 个合集
        </p>
      </div>
      <div class="d-flex ga-2 flex-wrap">
        <v-btn color="warning" variant="tonal" size="small" prepend-icon="mdi-plus" @click="openNew">新建合集</v-btn>
        <v-btn color="success" variant="tonal" size="small" prepend-icon="mdi-refresh" :loading="store.isLoading" @click="handleScan">扫描库</v-btn>
        <v-btn color="info" variant="tonal" size="small" prepend-icon="mdi-import" @click="triggerImport">导入数据</v-btn>
        <input type="file" ref="fileInput" @change="handleImport" accept=".zip" multiple class="d-none" />
        <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-download" @click="showEmbyImport = true">从 Emby 导入</v-btn>
        <v-btn color="warning" variant="tonal" size="small" prepend-icon="mdi-cloud-upload" @click="showEmbyApplyAll = true">应用所有到 Emby</v-btn>
        <v-btn color="accent" variant="tonal" size="small" prepend-icon="mdi-image-multiple" @click="showBatchPoster = true">批量生成海报</v-btn>
      </div>
    </div>

    <!-- 搜索栏 -->
    <v-text-field
      v-model="searchTerm"
      placeholder="搜索合集名称或简介..."
      prepend-inner-icon="mdi-magnify"
      density="compact"
      variant="outlined"
      clearable
      max-width="400"
      class="mb-4"
    />

    <!-- 加载中 -->
    <div v-if="store.isLoading && !store.collections.length" class="text-center pa-8">
      <v-progress-circular indeterminate color="primary" size="40" />
      <p class="mt-3 text-medium-emphasis">加载中...</p>
    </div>

    <!-- 合集卡片网格 -->
    <v-row v-else-if="filteredCollections.length" density="compact">
      <v-col v-for="col in filteredCollections" :key="col.filename" v-bind="uiStore.gridColProps">
        <v-card rounded="xl" hover variant="outlined" height="100%" class="d-flex flex-column cursor-pointer" @click="openDetail(col)">
          <!-- 海报 -->
          <v-img
            v-if="col.poster_path"
            :src="col.poster_path"
            aspect-ratio="2/3"
            cover
            class="flex-grow-0 collection-poster-img"
          >
            <template #error>
              <div class="d-flex align-center justify-center fill-height bg-surface-variant">
                <v-icon size="48" color="grey-lighten-1">mdi-folder-image</v-icon>
              </div>
            </template>
          </v-img>
          <v-sheet v-else rounded="0" class="poster-aspect d-flex align-center justify-center bg-surface-variant">
            <v-icon size="48" color="grey-lighten-1">mdi-folder-image</v-icon>
          </v-sheet>

          <!-- 信息 -->
          <v-card-text class="pa-3">
            <div class="text-body-2 font-weight-bold text-center text-truncate" :title="col.name || col.collection_name">{{ col.name || col.collection_name }}</div>
            <div v-if="col.overview" class="line-clamp-2 text-caption text-medium-emphasis mt-1 text-center">{{ col.overview }}</div>
          </v-card-text>

          <v-spacer />
        </v-card>
      </v-col>
    </v-row>

    <!-- 空状态 -->
    <v-card v-else variant="outlined" rounded="xl" class="pa-8">
      <div class="text-center">
        <v-icon size="64" color="grey-lighten-1">mdi-folder-open-outline</v-icon>
        <h3 class="text-h6 mt-3 mb-2">{{ searchTerm ? '未找到匹配的合集' : '暂无合集数据' }}</h3>
        <p class="text-caption text-medium-emphasis mb-4">
          {{ searchTerm ? '尝试更换关键词' : '点击「新建合集」创建你的第一个合集，或点击「扫描库」从文件系统发现已有合集' }}
        </p>
        <v-btn v-if="!searchTerm" color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openNew">
          新建合集
        </v-btn>
      </div>
    </v-card>

    <!-- 弹框 -->
    <EmbyImportDialog v-model="showEmbyImport" @refresh="store.loadCollections()" />
    <EmbyApplyAllDialog v-model="showEmbyApplyAll" />
    <BatchPosterDialog v-model="showBatchPoster" :collections="store.collections" @done="store.loadCollections()" />
  </v-container>
</template>

<style scoped>
/* 海报底部与文字区交界处也做圆角（顶部由卡片 overflow 裁切），半径跟随主题卡片圆角 */
.collection-poster-img {
  border-radius: var(--am-surface-radius, 16px);
}
</style>

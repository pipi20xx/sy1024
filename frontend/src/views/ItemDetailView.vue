<script setup lang="ts">
import { ref, computed, watch, onMounted, onDeactivated } from 'vue'
import { useRoute, useRouter } from 'vue-router'
defineOptions({ name: 'ItemDetailView' })
import { useDetailsStore } from '@/stores'
import { useNotification, useConfirm } from '@/composables'
import { updateMappingApi } from '@/api/tmdbBgmMapping'
import { getBangumiRecommendation } from '@/api/details'
import DetailsHeader from '@/components/details/DetailsHeader.vue'
import DetailsOverview from '@/components/details/DetailsOverview.vue'
import DetailsCastCrew from '@/components/details/DetailsCastCrew.vue'
import DetailsSeasons from '@/components/details/DetailsSeasons.vue'
import DetailsImages from '@/components/details/DetailsImages.vue'
import DetailsTags from '@/components/details/DetailsTags.vue'
import DetailsActions from '@/components/details/DetailsActions.vue'
import DetailsEditModal from '@/components/details/DetailsEditModal.vue'
import PatchNameModal from '@/components/details/PatchNameModal.vue'
import type { ItemType } from '@/types'

const route = useRoute()
const router = useRouter()
const store = useDetailsStore()
const { notify } = useNotification()
const { confirm } = useConfirm()
const isEmbyRefreshing = ref(false)

const activeTab = ref('seasons')
const showEditDialog = ref(false)
const showPatchNameDialog = ref(false)

// 快速添加 BGM 映射
const showAddBgmDialog = ref(false)
const addBgmIdInput = ref('')
const addBgmSeasonInput = ref(0)
const isAddingBgm = ref(false)

// BGM 映射信息（悬浮展示）
interface BgmRelationInfo {
  id: number
  name: string
  year: string
  source: string
  seasonNumber?: number
}
const bgmRelationList = ref<BgmRelationInfo[]>([])
const bgmMenuOpen = ref(false)
const bgmInfosLoading = ref(false)
const bgmInfosLoaded = ref(false)

async function loadBgmMappingInfos() {
  if (bgmInfosLoaded.value || bgmInfosLoading.value) return
  if (!store.currentItemId || !store.currentItemType) return
  bgmInfosLoading.value = true
  bgmInfosLoaded.value = false
  try {
    const rec = await getBangumiRecommendation(store.currentItemType, store.currentItemId)
    if (rec && rec.status === 'linked' && rec.bangumi_id) {
      const toInfo = (r: any): BgmRelationInfo => ({
        id: r.bangumi_id,
        name: r.bangumi_title || '',
        year: r.year || '',
        source: r.source || '',
        seasonNumber: r.season_number ?? undefined,
      })
      const list: BgmRelationInfo[] = Array.isArray(rec.relations) && rec.relations.length
        ? rec.relations.map(toInfo)
        : [toInfo(rec)]
      bgmRelationList.value = list.filter((r, i) => list.findIndex(x => x.id === r.id) === i)
    } else {
      bgmRelationList.value = []
    }
  } catch (e) {
    console.error('Failed to load BGM mapping infos:', e)
    bgmRelationList.value = []
  } finally {
    bgmInfosLoading.value = false
    bgmInfosLoaded.value = true
  }
}

function openAddBgmDialog() {
  addBgmIdInput.value = ''
  addBgmSeasonInput.value = 0
  showAddBgmDialog.value = true
}

async function handleAddBgmMapping() {
  const bgmId = parseInt(addBgmIdInput.value.trim())
  if (isNaN(bgmId)) {
    notify('请输入有效的 BGM ID', '', 'warning')
    return
  }
  const tmdbId = parseInt(store.currentItemId)
  if (isNaN(tmdbId)) return
  const tmdbType = isMovie.value ? 'movie' : 'tv'
  // 季号仅作备注，统一由用户填写
  const seasonKey = String(addBgmSeasonInput.value)
  isAddingBgm.value = true
  try {
    await updateMappingApi({
      tmdb_id: tmdbId,
      tmdb_type: tmdbType as any,
      season_mappings: { [seasonKey]: [bgmId] },
    })
    notify('添加成功', '', 'success')
    showAddBgmDialog.value = false
    // 重置懒加载状态，下次打开菜单时重新加载
    bgmRelationList.value = []
    bgmInfosLoaded.value = false
    bgmInfosLoading.value = false
    // 刷新详情以更新 has_bgm_mapping 状态
    await store.loadDetails()
  } catch (e: any) {
    notify('添加失败', e.message || '未知错误', 'error')
  } finally {
    isAddingBgm.value = false
  }
}

const isMovie = computed(() => store.currentItemType === 'tmdb-movies2')

const tabs = computed(() => {
  const t: { value: string; title: string; icon: string }[] = []
  if (!isMovie.value) {
    t.push({ value: 'seasons', title: '季集', icon: 'mdi-television-classic' })
  }
  t.push(
    { value: 'cast', title: '演职员', icon: 'mdi-account-group-outline' },
    { value: 'images', title: '图片', icon: 'mdi-image-multiple-outline' },
    { value: 'tags', title: '标签', icon: 'mdi-tag-multiple-outline' },
    { value: 'json', title: 'JSON', icon: 'mdi-code-block-braces' },
    { value: 'actions', title: '操作', icon: 'mdi-cog-outline' },
  )
  return t
})

const displayTitle = computed(() => {
  const d = store.itemDetails
  if (!d) return '详情'
  return d.name || d.title || d.full_metadata?.name || d.full_metadata?.title || '详情'
})

const displayYear = computed(() => {
  const d = store.itemDetails
  if (!d) return ''
  if (d.year) return `(${d.year})`
  const meta = d.full_metadata
  if (!meta) return ''
  const dateStr = meta.release_date || meta.first_air_date || ''
  return dateStr ? `(${dateStr.substring(0, 4)})` : ''
})

const tmdbUrl = computed(() => {
  if (!store.currentItemId) return ''
  return `https://www.themoviedb.org/${isMovie.value ? 'movie' : 'tv'}/${store.currentItemId}`
})

function handleBack() {
  router.back()
}

async function handleEmbyRefresh() {
  const ok = await confirm({
    title: '在 Emby 中刷新',
    content: '将触发 Emby 服务器重新读取该项目的元数据，确定要继续吗？',
    confirmColor: 'success',
  })
  if (!ok) return
  isEmbyRefreshing.value = true
  try {
    const success = await store.triggerEmbyRefresh()
    if (success) notify('已触发 Emby 刷新', '', 'success')
    else notify('Emby 刷新失败', '', 'error')
  } catch (e: any) {
    notify('Emby 刷新失败', e.message, 'error')
  } finally {
    isEmbyRefreshing.value = false
  }
}

// 从路由参数加载详情
async function loadFromRoute() {
  const itemType = route.params.itemType as string
  const tmdbId = route.params.tmdbId as string

  if (!itemType || !tmdbId) return

  const validType = itemType as ItemType
  // 只有当类型或ID变化时才重新加载
  if (store.currentItemType !== validType || store.currentItemId !== tmdbId) {
    await store.openPage(validType, tmdbId)
  }
}

onMounted(() => {
  loadFromRoute()
})

// keep-alive 停用时清理大对象，释放内存
onDeactivated(() => {
  store.previewImages = []
  store.webImages = []
  store.seasonWebImages = []
  store.episodeWebImages = []
})

// 监听路由变化（浏览器前进/后退）
watch(() => [route.params.itemType, route.params.tmdbId], () => {
  if (route.name === 'itemDetail') {
    loadFromRoute()
  }
})

// 切换条目时必须重置 BGM 懒加载状态：本页是 keep-alive 复用组件，
// 两个条目的 has_bgm_mapping 同为 true 时值 watcher 不会触发，会沿用上一个条目的 BGM 数据
watch(() => [store.currentItemType, store.currentItemId], () => {
  bgmMenuOpen.value = false
  bgmRelationList.value = []
  bgmInfosLoaded.value = false
  bgmInfosLoading.value = false
})

// 同一条目内映射状态变化（如刚添加映射）时重置
watch(() => store.itemDetails?.has_bgm_mapping, () => {
  bgmRelationList.value = []
  bgmInfosLoaded.value = false
  bgmInfosLoading.value = false
})

// 打开菜单时懒加载
watch(bgmMenuOpen, (open) => {
  if (open && store.itemDetails?.has_bgm_mapping) {
    loadBgmMappingInfos()
  }
})
</script>

<template>
  <v-container fluid class="pa-6 page-container tmdb-detail-view">
    <!-- 顶部导航条 -->
    <div class="d-flex align-center mb-2 flex-wrap ga-2">
      <v-btn variant="tonal" color="grey" prepend-icon="mdi-arrow-left" @click="handleBack" size="small">
        返回
      </v-btn>
      <v-divider vertical />
      <div class="text-h6 font-weight-bold text-truncate">
        {{ displayTitle }}
        <span v-if="displayYear" class="text-medium-emphasis text-body-1 ml-1">{{ displayYear }}</span>
      </div>
      <v-spacer />
      <!-- TMDB / Emby 跳转 -->
      <v-btn
        size="small"
        variant="tonal"
        color="info"
        :href="tmdbUrl"
        target="_blank"
        prepend-icon="mdi-open-in-new"
      >
        TMDB
      </v-btn>
      <v-btn
        v-if="store.embyWebLink"
        size="small"
        variant="tonal"
        color="success"
        :href="store.embyWebLink"
        target="_blank"
        prepend-icon="mdi-open-in-new"
      >
        Emby
      </v-btn>
      <v-divider vertical />
      <!-- 状态标签 -->
      <!-- 无 BGM：可点击添加 -->
      <v-chip
        v-if="store.itemDetails?.has_bgm_mapping !== undefined && !store.itemDetails.has_bgm_mapping"
        size="small" variant="tonal" color="grey" link
        @click="openAddBgmDialog"
      >
        <v-icon start size="x-small">mdi-link-off</v-icon>
        无BGM
        <v-tooltip activator="parent" location="bottom">点击添加 BGM 映射</v-tooltip>
      </v-chip>
      <!-- 有 BGM：悬浮显示详情和跳转链接 -->
      <v-menu
        v-else-if="store.itemDetails?.has_bgm_mapping"
        v-model="bgmMenuOpen"
        :close-on-content-click="false"
        location="bottom end"
        transition="scale-transition"
      >
        <template #activator="{ props }">
          <v-chip v-bind="props" size="small" variant="tonal" color="info" link>
            <v-icon start size="x-small">mdi-link-variant</v-icon>
            BGM
            <v-icon end size="x-small">mdi-chevron-down</v-icon>
          </v-chip>
        </template>
        <v-card min-width="280" max-width="360" rounded="lg" variant="outlined">
          <v-list density="compact" class="pa-0">
            <template v-for="(bgm, idx) in bgmRelationList" :key="`${bgm.id}-${idx}`">
              <v-divider v-if="idx > 0" />
              <v-list-item density="compact" class="px-3">
                <template #prepend>
                  <v-chip size="x-small" variant="flat" color="warning" label>{{ bgm.id }}</v-chip>
                </template>
                <v-list-item-title class="text-body-2 text-truncate">{{ bgm.name }}</v-list-item-title>
                <v-list-item-subtitle class="text-caption">
                  <template v-if="bgm.seasonNumber">S{{ bgm.seasonNumber }} · </template>{{ bgm.year || '未知日期' }}<template v-if="bgm.source"> · {{ bgm.source }}</template>
                </v-list-item-subtitle>
                <template #append>
                  <v-btn
                    size="x-small" variant="tonal" icon="mdi-open-in-new" color="info" density="comfortable"
                    :href="`https://bgm.tv/subject/${bgm.id}`" target="_blank"
                  />
                </template>
              </v-list-item>
            </template>
            <v-list-item v-if="bgmInfosLoading" density="compact">
              <v-progress-circular indeterminate size="16" width="2" color="primary" class="mr-2" />
              <span class="text-caption text-medium-emphasis">加载中...</span>
            </v-list-item>
            <v-list-item v-else-if="bgmInfosLoaded && bgmRelationList.length === 0" density="compact">
              <span class="text-caption text-medium-emphasis">未找到 BGM 信息</span>
            </v-list-item>
          </v-list>
        </v-card>
      </v-menu>
      <v-chip v-if="store.itemDetails?.source === 'override'" size="small" variant="tonal" color="warning">
        <v-icon start size="x-small">mdi-source-branch</v-icon>
        Override
      </v-chip>
      <v-chip v-else-if="store.itemDetails?.source === 'primary'" size="small" variant="tonal" color="success">
        <v-icon start size="x-small">mdi-source-commit</v-icon>
        Primary
      </v-chip>
      <v-chip v-if="store.itemDetails?.override_patches_exists" size="small" variant="tonal" color="info" link @click="showPatchNameDialog = true">
        <v-icon start size="x-small">mdi-file-document-edit</v-icon>
        Patches
      </v-chip>
      <v-chip v-if="store.embyWebLink" size="small" variant="tonal" color="success">已入库</v-chip>
      <v-chip v-else-if="store.itemDetails" size="small" variant="tonal" color="error">未入库</v-chip>
    </div>

    <!-- 操作按钮行：紧跟导航条下方 -->
    <div v-if="store.itemDetails" class="d-flex flex-wrap ga-2 justify-end mb-4">
      <v-btn size="small" variant="tonal" color="success" :loading="isEmbyRefreshing" @click="handleEmbyRefresh" prepend-icon="mdi-sync">刷新 Emby</v-btn>
      <v-btn size="small" variant="tonal" color="info" @click="store.copyItemToOverride()" prepend-icon="mdi-content-copy">补充到 Override</v-btn>
      <v-tooltip text="Primary 缓存不支持编辑，请先「补充到 Override」" :disabled="store.itemDetails?.source === 'override'">
        <template #activator="{ props }">
          <span v-bind="props">
            <v-btn size="small" color="primary" variant="tonal" :disabled="store.itemDetails?.source !== 'override'" @click="showEditDialog = true" prepend-icon="mdi-pencil">编辑</v-btn>
          </span>
        </template>
      </v-tooltip>
    </div>

    <!-- 加载中 -->
    <div v-if="store.isLoading" class="loading-state d-flex flex-column justify-center align-center">
      <v-progress-circular indeterminate color="primary" size="64" />
      <p class="mt-4 text-medium-emphasis">加载详情...</p>
    </div>

    <!-- 详情内容 -->
    <template v-else-if="store.itemDetails">
      <!-- 头部信息 + 海报 -->
      <DetailsHeader />

      <!-- 概览内容直接展示（不作为独立 tab） -->
      <div class="mt-2">
        <DetailsOverview />
      </div>

      <!-- 标签页 -->
      <v-tabs v-model="activeTab" color="primary" class="mt-4">
        <v-tab v-for="tab in tabs" :key="tab.value" :value="tab.value">
          <v-icon start>{{ tab.icon }}</v-icon>
          {{ tab.title }}
        </v-tab>
      </v-tabs>

      <v-divider />

      <!-- 标签页内容 — 与合集详情页一致使用 v-window：
           内容首次激活后常驻 DOM 仅切换可见性，避免光学渲染器在
           v-if 销毁/重建后丢失部分卡片的水漾表面 -->
      <v-window v-model="activeTab" class="mt-4">
        <v-window-item value="cast">
          <DetailsCastCrew />
        </v-window-item>
        <v-window-item value="seasons">
          <DetailsSeasons />
        </v-window-item>
        <v-window-item value="images">
          <DetailsImages />
        </v-window-item>
        <v-window-item value="tags">
          <DetailsTags />
        </v-window-item>
        <v-window-item value="json">
          <!-- JSON 原文限制在内部滚动容器内：无限制的 <pre> 会把文档撑到上万像素，
               scroll 光学画布的 backing buffer 有 3072px 高度上限，被拉伸后整页玻璃都会模糊 -->
          <v-card variant="outlined" rounded="xl" class="pa-4">
            <pre
              class="text-caption json-viewer json-viewer--scroll"
            >{{ JSON.stringify(store.itemDetails?.full_metadata, null, 2) }}</pre>
          </v-card>
        </v-window-item>
        <v-window-item value="actions">
          <DetailsActions />
        </v-window-item>
      </v-window>

      <!-- 编辑元数据弹框 -->
      <DetailsEditModal v-model="showEditDialog" />
      <PatchNameModal v-model="showPatchNameDialog" />

    <!-- 快速添加 BGM 映射弹框 -->
    <v-dialog v-model="showAddBgmDialog" max-width="450">
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-link-plus" class="mr-2" />
          添加 BGM 映射
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showAddBgmDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <v-row density="compact">
            <v-col cols="4">
              <v-text-field
                v-model.number="addBgmSeasonInput"
                label="季号"
                type="number"
                density="compact"
                variant="outlined"
                hide-details
              />
            </v-col>
            <v-col cols="8">
              <v-text-field
                v-model="addBgmIdInput"
                label="BGM ID"
                density="compact"
                variant="outlined"
                placeholder="输入 Bangumi Subject ID"
                hide-details
                @keyup.enter="handleAddBgmMapping"
              />
            </v-col>
          </v-row>
          <div class="text-caption text-medium-emphasis mt-2">
            季号仅作备注，默认 S0
          </div>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showAddBgmDialog = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-check" :loading="isAddingBgm" @click="handleAddBgmMapping">添加</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    </template>

    <!-- 空状态 -->
    <div v-else class="loading-state d-flex flex-column justify-center align-center">
      <v-icon size="80" color="grey">mdi-help-circle-outline</v-icon>
      <p class="mt-4 text-h6 text-medium-emphasis">未找到项目详情</p>
      <v-btn variant="tonal" color="primary" class="mt-4" @click="handleBack">返回首页</v-btn>
    </div>
  </v-container>
</template>

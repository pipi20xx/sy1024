<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
defineOptions({ name: 'ActorsView' })
import { useActorStore, useUiStore } from '@/stores'
import {
  updateActorsFromTmdb,
  updateAllActorsFromTmdb,
  updateActorsOverride,
  getMergePreview,
  executeMerge,
  type ActorItem,
} from '@/api/actors'
import { useNotification, useConfirm, useInfiniteScroll } from '@/composables'

const store = useActorStore()
const router = useRouter()
const uiStore = useUiStore()
const { notify } = useNotification()
const { confirm } = useConfirm()

const totalCount = computed(() => store.total || store.actors.length)
const searchInput = ref('')

// 选中项（批量操作用）
const selectedIds = ref<number[]>([])

// 筛选
const duplicateFilterOptions = [
  { title: '全部显示', value: 'all' },
  { title: '重复 TMDB ID', value: 'tmdb_id' },
  { title: '重复姓名', value: 'name' },
  { title: '重复原始姓名', value: 'original_name' },
]

// 合并 - 第1步：选择类型
const showMergeTypeDialog = ref(false)
const mergeType = ref('tmdb_id')
const isScanningMerge = ref(false)

// 合并 - 第2步：预览确认
const showMergePreviewDialog = ref(false)
const mergePlan = ref<any[]>([])
const isExecutingMerge = ref(false)

useInfiniteScroll({
  onLoad: () => store.loadMore(),
  hasMore: () => store.hasMore,
  isLoading: () => store.loading,
})

onMounted(() => { store.fetchActors(true) })

// ── 搜索 ──
async function handleSearch() {
  store.search = searchInput.value
  await store.fetchActors(true)
}

async function handleFilterChange() {
  await store.fetchActors(true)
}

// ── 跳转详情页 ──
function openDetail(actor: ActorItem) {
  router.push({ name: 'actorDetail', params: { actorId: actor.id } })
}

// ── 选中 ──
function toggleSelect(id: number) {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) selectedIds.value.splice(idx, 1)
  else selectedIds.value.push(id)
}

function isSelected(id: number) {
  return selectedIds.value.includes(id)
}

// ── 批量刷新选中 ──
async function handleBatchUpdateFromTmdb() {
  if (selectedIds.value.length === 0) return
  const ok = await confirm({
    title: '批量从 TMDB 更新',
    content: `确定要从 TMDB 更新选中的 ${selectedIds.value.length} 位演员的信息吗？`,
  })
  if (!ok) return
  try {
    await updateActorsFromTmdb(selectedIds.value)
    notify('批量更新任务已提交', '', 'success')
    selectedIds.value = []
  } catch (e: any) {
    notify('启动批量更新失败', e.message, 'error')
  }
}

// ── 更新全部 ──
async function handleUpdateAllFromTmdb() {
  const ok = await confirm({
    title: '全量更新演员信息',
    content: `系统将启动后台任务，自动从 TMDB 更新库中所有演员 (${store.total} 位) 的姓名和原名。任务耗时较长，建议在空闲时间执行。是否继续？`,
    confirmColor: 'warning',
  })
  if (!ok) return
  try {
    const res = await updateAllActorsFromTmdb()
    if (res.success) notify('全量更新任务已启动', '', 'success')
  } catch (e: any) {
    notify('启动任务失败', e.message, 'error')
  }
}

// ── 一键更新 Override ──
async function handleUpdateOverride() {
  const ok = await confirm({
    title: '一键更新 Override',
    content: '系统将遍历所有本地 JSON 文件，根据数据库中的标准姓名和 ID 强制修正文件内容。这会直接修改本地文件，建议先执行备份。是否继续？',
  })
  if (!ok) return
  try {
    const res = await updateActorsOverride()
    if (res.success) notify('更新任务已在后台启动', '', 'success')
  } catch (e: any) {
    notify('启动更新任务失败', e.message, 'error')
  }
}

// ── 从 Override 导入 ──
async function handleImport() {
  const success = await store.importFromOverrideBg()
  if (success) notify('后台导入任务已启动', '', 'success')
}

// ── 清空 ──
async function handleClearAll() {
  const ok = await confirm({
    title: '清空演员库',
    content: `确认清空全部 ${store.total} 条演员数据？此操作不可恢复！`,
    confirmColor: 'error',
  })
  if (!ok) return
  const success = await store.removeAll()
  if (success) notify('已清空', '', 'success')
}

// ── 合并 - 第1步：选择类型 ──
function openMergeTypeDialog() {
  mergeType.value = 'tmdb_id'
  showMergeTypeDialog.value = true
}

async function handleStartMergeScan() {
  showMergeTypeDialog.value = false
  showMergePreviewDialog.value = true
  isScanningMerge.value = true
  mergePlan.value = []
  try {
    mergePlan.value = await getMergePreview(mergeType.value)
  } catch (e: any) {
    notify('扫描重复数据失败', e.message, 'error')
    showMergePreviewDialog.value = false
  } finally {
    isScanningMerge.value = false
  }
}

// ── 合并 - 第2步：确认执行 ──
async function handleConfirmMerge() {
  const ok = await confirm({
    title: '确认合并操作',
    content: `你将执行 ${mergePlan.value.length} 组数据的合并，系统将保留建议的姓名和原始姓名，并删除其余重复记录。此操作不可撤销，是否继续？`,
    confirmColor: 'warning',
  })
  if (!ok) return
  isExecutingMerge.value = true
  try {
    const res = await executeMerge(mergePlan.value)
    notify(res.message || '合并完成', '', 'success')
    showMergePreviewDialog.value = false
    await store.fetchActors(true)
  } catch (e: any) {
    notify('执行合并失败', e.message, 'error')
  } finally {
    isExecutingMerge.value = false
  }
}
</script>

<template>
  <v-container fluid class="pa-6">
    <!-- 页头 -->
    <div class="d-flex flex-wrap align-center mb-6 ga-3">
      <div class="flex-grow-1">
        <h1 class="text-h5 font-weight-bold">演员库</h1>
        <p class="text-caption text-medium-emphasis mt-1">
          管理影视演职人员数据 · 共 {{ totalCount }} 人
        </p>
      </div>
      <div class="d-flex ga-2 flex-wrap">
        <v-btn
          color="info" variant="tonal" size="small" prepend-icon="mdi-sync"
          :disabled="selectedIds.length === 0"
          @click="handleBatchUpdateFromTmdb"
        >
          更新选中 ({{ selectedIds.length }})
        </v-btn>
        <v-btn color="success" variant="tonal" size="small" prepend-icon="mdi-cloud-download" @click="handleUpdateAllFromTmdb">更新全部</v-btn>
        <v-btn color="warning" variant="tonal" size="small" prepend-icon="mdi-merge" @click="openMergeTypeDialog">合并重复</v-btn>
        <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-file-edit" @click="handleUpdateOverride">更新 Override</v-btn>
        <v-btn color="info" variant="tonal" size="small" prepend-icon="mdi-database-import-outline" @click="handleImport">从 Override 导入</v-btn>
        <v-btn color="error" variant="tonal" size="small" prepend-icon="mdi-delete-sweep" @click="handleClearAll">清空</v-btn>
      </div>
    </div>

    <!-- 搜索 + 筛选 -->
    <div class="d-flex ga-3 mb-4 align-center flex-wrap">
      <v-text-field
        v-model="searchInput"
        placeholder="搜索姓名或 TMDB ID..."
        density="compact"
        variant="outlined"
        prepend-inner-icon="mdi-magnify"
        clearable
        hide-details
        @keyup.enter="handleSearch"
        @click:clear="store.search = ''; store.fetchActors(true)"
        class="filter-field"
      />
      <v-select
        v-model="store.duplicateType"
        :items="duplicateFilterOptions"
        density="compact"
        variant="outlined"
        hide-details
        class="mw-180px"
        @update:model-value="handleFilterChange"
      />
      <span v-if="selectedIds.length" class="text-caption text-primary">
        已选 {{ selectedIds.length }} 项
        <v-btn size="small" variant="tonal" @click="selectedIds = []">取消选择</v-btn>
      </span>
      <span class="text-caption text-medium-emphasis">共 {{ totalCount }} 个</span>
    </div>

    <!-- 加载中 -->
    <div v-if="store.loading && !store.actors.length" class="text-center pa-8">
      <v-progress-circular indeterminate color="primary" size="40" />
      <p class="mt-3 text-medium-emphasis">加载中...</p>
    </div>

    <!-- 演员卡片网格（海报样式） -->
    <v-row v-else-if="store.actors.length" density="compact">
      <v-col v-for="actor in store.actors" :key="actor.id" v-bind="uiStore.gridColProps">
        <v-card
          rounded="xl"
          hover
          variant="outlined"
          class="h-100 d-flex flex-column actor-poster-card"
          :class="{ 'actor-poster-card--selected': isSelected(actor.id) }"
          @click="openDetail(actor)"
        >
          <!-- 选中勾选标记 -->
          <div class="actor-card-check" @click.stop="toggleSelect(actor.id)">
            <v-icon
              :icon="isSelected(actor.id) ? 'mdi-check-circle' : 'mdi-checkbox-blank-circle-outline'"
              :color="isSelected(actor.id) ? 'primary' : 'white'"
              size="28"
            />
          </div>

          <!-- 头像图片 -->
          <v-img
            v-if="actor.profile_path"
            :src="`/tmdb-mock/t/p/w342${actor.profile_path}`"
            aspect-ratio="2/3"
            cover
            class="flex-grow-0 poster-rounded"
          >
            <template #error>
              <div class="d-flex align-center justify-center fill-height bg-surface-variant">
                <v-icon size="56" color="grey-lighten-1">mdi-account</v-icon>
              </div>
            </template>
          </v-img>
          <v-sheet v-else rounded="0" class="poster-aspect d-flex align-center justify-center bg-surface-variant">
            <v-icon size="56" color="grey-lighten-1">mdi-account</v-icon>
          </v-sheet>

          <!-- 信息 -->
          <v-card-text class="pa-2 flex-grow-1 d-flex flex-column justify-center">
            <div class="text-body-2 font-weight-bold text-center text-truncate" :title="actor.name">
              {{ actor.name }}
            </div>
            <div v-if="actor.original_name && actor.original_name !== actor.name"
              class="text-caption text-medium-emphasis text-center text-truncate" :title="actor.original_name">
              {{ actor.original_name }}
            </div>
            <div class="text-center mt-1">
              <v-chip size="x-small" variant="tonal" label>{{ actor.tmdb_id }}</v-chip>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- 滚动加载提示 -->
    <div v-if="store.loading && store.actors.length" class="text-center pa-4">
      <v-progress-circular indeterminate size="24" color="primary" />
      <span class="ml-2 text-caption text-medium-emphasis">加载中...</span>
    </div>
    <div v-else-if="!store.hasMore && store.actors.length" class="text-center pa-2 text-caption text-medium-emphasis">
      已全部加载 ({{ store.actors.length }} / {{ totalCount }})
    </div>

    <!-- 空状态 -->
    <v-card v-if="!store.loading && !store.actors.length" variant="outlined" rounded="xl" class="pa-8">
      <div class="text-center">
        <v-icon size="64" color="grey-lighten-1">mdi-account-off-outline</v-icon>
        <div class="text-h6 mt-3 mb-2">暂无演员数据</div>
        <div class="text-caption text-medium-emphasis mb-4">
          从 Override 缓存导入演员数据，或扫描媒体库自动填充
        </div>
        <v-btn color="info" variant="tonal" prepend-icon="mdi-database-import-outline" @click="handleImport">
          从 Override 导入
        </v-btn>
      </div>
    </v-card>

    <!-- 合并 - 第1步：选择合并类型 -->
    <v-dialog v-model="showMergeTypeDialog" max-width="480">
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-merge" class="mr-2" />
          一键合并重复项
          <v-spacer />
          <v-btn size="small" variant="text" icon="mdi-close" @click="showMergeTypeDialog = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4">
          <p class="text-body-2 mb-4">请选择合并的依据字段：</p>
          <v-radio-group v-model="mergeType" hide-details>
            <v-radio value="tmdb_id" label="按 TMDB ID 合并（推荐）" />
            <v-radio value="name" label="按 姓名合并" />
            <v-radio value="original_name" label="按 原始姓名合并" />
          </v-radio-group>
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showMergeTypeDialog = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-magnify" @click="handleStartMergeScan">开始扫描</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 合并 - 第2步：预览确认 -->
    <v-dialog v-model="showMergePreviewDialog" max-width="1100" width="95vw" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-merge" class="mr-2" />
          确认合并方案
          <v-spacer />
          <v-btn size="small" variant="text" icon="mdi-close" @click="showMergePreviewDialog = false" />
        </v-card-title>
        <v-divider />

        <!-- 扫描中 -->
        <v-card-text v-if="isScanningMerge" class="text-center pa-8">
          <v-progress-circular indeterminate color="primary" size="40" />
          <p class="mt-3 text-medium-emphasis">正在查找重复数据...</p>
        </v-card-text>

        <!-- 无重复 -->
        <v-card-text v-else-if="mergePlan.length === 0" class="text-center pa-8">
          <v-icon size="48" color="grey-lighten-1" class="mb-2">mdi-check-circle-outline</v-icon>
          <p class="text-body-2 text-medium-emphasis">库中没有发现该类型的重复项</p>
        </v-card-text>

        <!-- 预览表格 -->
        <v-card-text v-else class="pt-4">
          <p class="text-body-2 text-medium-emphasis mb-3">
            已发现 {{ mergePlan.length }} 组重复数据。你可以手动调整合并后的姓名和原始姓名。
          </p>
          <v-table density="compact" class="merge-table">
            <thead>
              <tr>
                <th class="w-120px">重复项值</th>
                <th class="w-140px">主 TMDB ID</th>
                <th>合并后的姓名</th>
                <th>合并后的原始姓名</th>
                <th class="w-60px">条数</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(group, index) in mergePlan" :key="index">
                <td>
                  <span class="text-warning font-weight-bold">{{ group.merge_value }}</span>
                </td>
                <td>
                  <v-select
                    v-model="group.suggested_tmdb_id"
                    :items="group.tmdb_id_options?.map((id: number) => ({ title: String(id), value: id })) || []"
                    density="compact"
                    variant="outlined"
                    hide-details
                    class="miw-120px"
                  />
                </td>
                <td>
                  <v-combobox
                    v-model="group.suggested_name"
                    :items="group.name_options || []"
                    density="compact"
                    variant="outlined"
                    hide-details
                    class="miw-150px"
                  />
                </td>
                <td>
                  <v-combobox
                    v-model="group.suggested_original_name"
                    :items="group.original_name_options || []"
                    density="compact"
                    variant="outlined"
                    hide-details
                    class="miw-150px"
                  />
                </td>
                <td>{{ group.count }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>

        <v-divider />
        <v-card-actions>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showMergePreviewDialog = false">取消</v-btn>
          <v-btn
            color="warning" variant="tonal"
            prepend-icon="mdi-merge"
            :disabled="mergePlan.length === 0"
            :loading="isExecutingMerge"
            @click="handleConfirmMerge"
          >
            确认合并并删除重复项
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<style scoped>
.actor-poster-card {
  position: relative;
  transition: all 0.2s ease;
  cursor: pointer;
}

/* 海报圆角由全局工具类 poster-rounded（utilities.css）统一提供 */

.actor-poster-card--selected {
  border: 2px solid rgb(var(--v-theme-primary)) !important;
  box-shadow: 0 0 0 1px rgb(var(--v-theme-primary)) !important;
}

.actor-card-check {
  position: absolute;
  top: 6px;
  right: 6px;
  z-index: 2;
  cursor: pointer;
  filter: drop-shadow(0 1px 3px rgba(0, 0, 0, 0.6));
}
</style>

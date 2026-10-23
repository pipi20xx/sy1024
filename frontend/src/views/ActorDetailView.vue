<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
defineOptions({ name: 'ActorDetailView' })
import { useActorStore } from '@/stores'
import {
  getActorDetail,
  getActorByTmdbId,
  createOrGetActorByTmdbId,
  refreshActorFromTmdb,
  updateActor,
  type ActorItem,
} from '@/api/actors'
import { useNotification, useConfirm } from '@/composables'

const route = useRoute()
const router = useRouter()
const store = useActorStore()
const { notify } = useNotification()
const { confirm } = useConfirm()

// ── 状态 ──
const isLoading = ref(false)
const isEditing = ref(false)
const isUpdatingTmdb = ref(false)
const isFetchingTmdb = ref(false)
const actorData = ref<ActorItem | null>(null)
const activeTab = ref('basic')

// 编辑表单
const editForm = ref<{
  tmdb_id: number
  name: string
  original_name: string
  duplicate_tmdb_id: string
}>({ tmdb_id: 0, name: '', original_name: '', duplicate_tmdb_id: '' })

// ── 计算属性 ──
const actorId = computed(() => {
  const id = route.params.actorId
  return id ? Number(id) : 0
})
const tmdbIdParam = computed(() => {
  const id = route.params.tmdbId
  return id ? Number(id) : 0
})
const isTmdbRoute = computed(() => route.name === 'actorDetailByTmdbId')

const profileUrl = computed(() => {
  if (!actorData.value?.profile_path) return ''
  return `/tmdb-mock/t/p/w342${actorData.value.profile_path}`
})

const tmdbPersonUrl = computed(() => {
  if (!actorData.value?.tmdb_id) return ''
  return `https://www.themoviedb.org/person/${actorData.value.tmdb_id}`
})

const metadata = computed(() => actorData.value?.metadata || null)

const genderText = computed(() => {
  const g = metadata.value?.gender
  if (g === 1) return '女'
  if (g === 2) return '男'
  return '未知'
})

// ── 初始化 ──
onMounted(() => loadDetails())

watch(() => [route.params.actorId, route.params.tmdbId], () => {
  if (route.name === 'actorDetail' || route.name === 'actorDetailByTmdbId') loadDetails()
})

async function loadDetails() {
  isLoading.value = true
  actorData.value = null
  isFetchingTmdb.value = false
  try {
    let data: ActorItem
    if (isTmdbRoute.value && tmdbIdParam.value) {
      // 通过 TMDB ID 进入：先查库，不在则自动创建
      try {
        data = await getActorByTmdbId(tmdbIdParam.value)
      } catch (e: any) {
        // 404 = 不在库中，自动从 TMDB 创建
        if (e.message?.includes('404') || e.message?.includes('未找到')) {
          isFetchingTmdb.value = true
          data = await createOrGetActorByTmdbId(tmdbIdParam.value)
          isFetchingTmdb.value = false
        } else {
          throw e
        }
      }
      // 如果没有 metadata，自动同步获取
      if (!data.metadata) {
        isFetchingTmdb.value = true
        try {
          data = await refreshActorFromTmdb(data.id)
        } catch (e: any) {
          notify('从 TMDB 获取元数据失败', e.message, 'warning')
        } finally {
          isFetchingTmdb.value = false
        }
      }
    } else {
      // 通过内部 ID 进入
      if (!actorId.value) return
      data = await getActorDetail(actorId.value)
      if (!data.metadata) {
        isFetchingTmdb.value = true
        try {
          data = await refreshActorFromTmdb(actorId.value)
        } catch (e: any) {
          notify('从 TMDB 获取元数据失败', e.message, 'warning')
        } finally {
          isFetchingTmdb.value = false
        }
      }
    }
    actorData.value = data
    editForm.value = {
      tmdb_id: data.tmdb_id || 0,
      name: data.name || '',
      original_name: data.original_name || '',
      duplicate_tmdb_id: data.duplicate_tmdb_id || '',
    }
  } catch (e: any) {
    notify('加载失败', e.message, 'error')
  } finally {
    isLoading.value = false
  }
}

// ── 操作 ──
function handleBack() {
  router.push({ name: 'actors' })
}

function startEdit() {
  if (actorData.value) {
    editForm.value = {
      tmdb_id: actorData.value.tmdb_id || 0,
      name: actorData.value.name || '',
      original_name: actorData.value.original_name || '',
      duplicate_tmdb_id: actorData.value.duplicate_tmdb_id || '',
    }
  }
  isEditing.value = true
}

function cancelEdit() {
  isEditing.value = false
}

async function handleSaveEdit() {
  if (!actorData.value) return
  // 处理 duplicate_tmdb_id：提取数字，去重
  let dupId = editForm.value.duplicate_tmdb_id
  if (dupId) {
    const matches = dupId.match(/\d+/g)
    dupId = matches ? Array.from(new Set(matches)).join(',') : ''
  }
  try {
    const updated = await updateActor(actorData.value.id, {
      tmdb_id: editForm.value.tmdb_id,
      name: editForm.value.name,
      original_name: editForm.value.original_name,
      duplicate_tmdb_id: dupId,
    })
    actorData.value = { ...actorData.value, ...updated }
    // 同步更新 store 列表中的数据
    const index = store.actors.findIndex(a => a.id === actorData.value!.id)
    if (index !== -1) store.actors[index] = { ...store.actors[index], ...updated }
    notify('保存成功', '', 'success')
    isEditing.value = false
  } catch (e: any) {
    notify('保存失败', e.message, 'error')
  }
}

async function handleUpdateFromTmdb() {
  if (!actorData.value) return
  const ok = await confirm({
    title: '从 TMDB 更新',
    content: `确定要从 TMDB 获取「${actorData.value.name}」的最新信息吗？`,
  })
  if (!ok) return
  isUpdatingTmdb.value = true
  try {
    const updated = await refreshActorFromTmdb(actorData.value.id)
    actorData.value = updated
    // 同步更新 store 列表中的数据
    const index = store.actors.findIndex(a => a.id === updated.id)
    if (index !== -1) store.actors[index] = { ...store.actors[index], ...updated }
    notify('更新成功', '', 'success')
  } catch (e: any) {
    notify('更新失败', e.message, 'error')
  } finally {
    isUpdatingTmdb.value = false
  }
}

async function handleDelete() {
  if (!actorData.value) return
  const ok = await confirm({
    title: '删除演员',
    content: `确认删除演员「${actorData.value.name}」吗？此操作不可恢复。`,
    confirmColor: 'error',
  })
  if (!ok) return
  const success = await store.removeActor(actorData.value.id)
  if (success) {
    notify('已删除', '', 'success')
    router.replace({ name: 'actors' })
  }
}
</script>

<template>
  <v-container fluid class="pa-6 page-container person-detail-view">
    <!-- 顶部导航条 -->
    <div class="d-flex align-center mb-4 flex-wrap ga-2">
      <v-btn variant="tonal" color="grey" prepend-icon="mdi-arrow-left" @click="handleBack" size="small">
        返回演员库
      </v-btn>
      <v-divider vertical />
      <div class="text-h6 font-weight-bold text-truncate">
        {{ actorData?.name || '演员详情' }}
      </div>
      <span v-if="actorData?.original_name && actorData.original_name !== actorData.name"
        class="text-medium-emphasis text-body-2">
        {{ actorData.original_name }}
      </span>
      <v-spacer />
      <!-- TMDB 跳转 -->
      <v-btn
        v-if="actorData?.tmdb_id"
        size="small"
        variant="tonal"
        color="info"
        :href="tmdbPersonUrl"
        target="_blank"
        prepend-icon="mdi-open-in-new"
      >
        TMDB
      </v-btn>
    </div>

    <!-- 加载中 -->
    <div v-if="isLoading" class="loading-state d-flex flex-column justify-center align-center">
      <v-progress-circular indeterminate color="primary" size="64" />
      <p class="mt-4 text-medium-emphasis">
        {{ isFetchingTmdb ? '正在从 TMDB 获取元数据...' : '加载详情...' }}
      </p>
    </div>

    <!-- 详情内容 -->
    <template v-else-if="actorData">
      <!-- 操作按钮行 -->
      <div class="d-flex flex-wrap ga-2 justify-end mb-4">
        <v-btn size="small" variant="tonal" color="info" prepend-icon="mdi-refresh"
          :loading="isUpdatingTmdb" :disabled="isUpdatingTmdb"
          @click="handleUpdateFromTmdb">
          从 TMDB 更新
        </v-btn>
        <v-btn v-if="!isEditing" size="small" color="primary" variant="tonal"
          prepend-icon="mdi-pencil" @click="startEdit">
          编辑
        </v-btn>
        <template v-else>
          <v-btn size="small" variant="tonal" color="primary" prepend-icon="mdi-content-save"
            @click="handleSaveEdit">
            保存
          </v-btn>
          <v-btn size="small" variant="tonal" color="grey" prepend-icon="mdi-close"
            @click="cancelEdit">
            取消
          </v-btn>
        </template>
        <v-btn size="small" variant="tonal" color="error" prepend-icon="mdi-delete-outline"
          @click="handleDelete">
          删除
        </v-btn>
      </div>

      <v-row>
        <!-- 左侧：头像 -->
        <v-col cols="12" sm="6" md="4" lg="3">
          <v-img
            v-if="profileUrl"
            :src="profileUrl"
            aspect-ratio="2/3"
            max-width="320"
            rounded="xl"
            cover
            class="mx-auto"
          >
            <template #error>
              <div class="d-flex align-center justify-center fill-height bg-surface-variant">
                <v-icon size="80" color="grey-lighten-1">mdi-account</v-icon>
              </div>
            </template>
          </v-img>
          <v-sheet v-else rounded="xl" class="d-flex align-center justify-center bg-surface-variant mx-auto"
            width="280" height="420">
            <v-icon size="80" color="grey-lighten-1">mdi-account</v-icon>
          </v-sheet>

          <!-- ID 信息 -->
          <div class="d-flex flex-wrap ga-2 mt-3 justify-center">
            <v-chip size="small" variant="tonal" label color="info">
              <v-icon start size="x-small">mdi-identifier</v-icon>
              TMDB: {{ actorData.tmdb_id }}
            </v-chip>
            <v-chip v-if="actorData.duplicate_tmdb_id" size="small" variant="tonal" color="warning" label>
              重复: {{ actorData.duplicate_tmdb_id }}
            </v-chip>
          </div>
        </v-col>

        <!-- 右侧：详情内容 -->
        <v-col cols="12" sm="6" md="8" lg="9">
          <v-tabs v-model="activeTab" density="compact" show-arrows>
            <v-tab value="basic">基本信息</v-tab>
            <v-tab value="json">原始 JSON</v-tab>
          </v-tabs>

          <v-divider class="mb-4" />

          <v-window v-model="activeTab">
            <!-- ═══ 基本信息 ═══ -->
            <v-window-item value="basic">
              <!-- 编辑模式 -->
              <template v-if="isEditing">
                <v-text-field v-model="editForm.tmdb_id" label="TMDB ID" type="number"
                  density="compact" variant="outlined" class="mb-3" />
                <v-text-field v-model="editForm.name" label="中文姓名"
                  density="compact" variant="outlined" class="mb-3" />
                <v-text-field v-model="editForm.original_name" label="原始姓名"
                  density="compact" variant="outlined" class="mb-3" />
                <v-text-field v-model="editForm.duplicate_tmdb_id" label="重复 TMDB ID（多个用逗号分隔）"
                  density="compact" variant="outlined" placeholder="如：12345,67890" />
              </template>

              <!-- 展示模式 -->
              <template v-else>
                <div class="text-h5 font-weight-bold mb-1">{{ actorData.name }}</div>
                <div v-if="actorData.original_name && actorData.original_name !== actorData.name"
                  class="text-body-1 text-medium-emphasis mb-4">
                  {{ actorData.original_name }}
                </div>

                <template v-if="metadata">
                  <!-- 生平简介 -->
                  <div v-if="metadata.biography" class="mb-4">
                    <div class="text-subtitle-2 font-weight-bold mb-1">
                      <v-icon start size="18">mdi-text-account</v-icon>
                      生平简介
                    </div>
                    <div class="text-body-2 pre-wrap biography-text">
                      {{ metadata.biography }}
                    </div>
                  </div>

                  <!-- 基本信息 -->
                  <div class="d-flex flex-wrap ga-6 mb-4">
                    <div v-if="metadata.birthday">
                      <div class="text-caption text-medium-emphasis font-weight-bold">生日</div>
                      <div class="text-body-2">{{ metadata.birthday }}</div>
                    </div>
                    <div v-if="metadata.place_of_birth">
                      <div class="text-caption text-medium-emphasis font-weight-bold">出生地</div>
                      <div class="text-body-2">{{ metadata.place_of_birth }}</div>
                    </div>
                    <div v-if="metadata.known_for_department">
                      <div class="text-caption text-medium-emphasis font-weight-bold">知名领域</div>
                      <div class="text-body-2">{{ metadata.known_for_department }}</div>
                    </div>
                    <div v-if="metadata.gender !== undefined">
                      <div class="text-caption text-medium-emphasis font-weight-bold">性别</div>
                      <div class="text-body-2">{{ genderText }}</div>
                    </div>
                    <div v-if="metadata.deathday">
                      <div class="text-caption text-medium-emphasis font-weight-bold">逝世</div>
                      <div class="text-body-2">{{ metadata.deathday }}</div>
                    </div>
                    <div v-if="metadata.popularity !== undefined">
                      <div class="text-caption text-medium-emphasis font-weight-bold">热度</div>
                      <div class="text-body-2">{{ metadata.popularity.toFixed(1) }}</div>
                    </div>
                  </div>

                  <!-- 别名 -->
                  <div v-if="metadata.also_known_as?.length" class="mb-4">
                    <div class="text-subtitle-2 font-weight-bold mb-2">
                      <v-icon start size="18">mdi-tag-multiple</v-icon>
                      别名
                    </div>
                    <div class="d-flex flex-wrap ga-1">
                      <v-chip v-for="aka in metadata.also_known_as" :key="aka" size="small" variant="tonal">
                        {{ aka }}
                      </v-chip>
                    </div>
                  </div>
                </template>

                <v-alert v-else type="info" variant="tonal" density="compact" class="mt-4">
                  尚未从 TMDB 获取完整元数据，请点击上方「从 TMDB 更新」按钮来拉取详细信息。
                </v-alert>
              </template>
            </v-window-item>

            <!-- ═══ 原始 JSON ═══ -->
            <v-window-item value="json">
              <v-card variant="outlined" rounded="xl" class="pa-4">
                <pre class="text-caption json-viewer">{{ JSON.stringify(actorData, null, 2) }}</pre>
              </v-card>
            </v-window-item>
          </v-window>
        </v-col>
      </v-row>
    </template>

    <!-- 空状态 -->
    <div v-else class="loading-state d-flex flex-column justify-center align-center">
      <v-icon size="80" color="grey">mdi-account-question-outline</v-icon>
      <p class="mt-4 text-h6 text-medium-emphasis">未找到演员信息</p>
      <v-btn variant="tonal" color="primary" class="mt-4" @click="handleBack">返回演员库</v-btn>
    </div>
  </v-container>
</template>

<style scoped>
/* 生平简介行高 */
.biography-text {
  line-height: 1.7;
}
</style>

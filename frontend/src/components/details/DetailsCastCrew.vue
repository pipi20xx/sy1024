<script setup lang="ts">
import { ref, computed, watch, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useDetailsStore, useAiStore } from '@/stores'
import { getTvAggregatedCredits } from '@/api/items'
import { batchTranslationApi } from '@/api/ai'
import { useNotification } from '@/composables'

const router = useRouter()
const store = useDetailsStore()
const aiStore = useAiStore()
const { notify } = useNotification()

const isMovie = computed(() => store.currentItemType === 'tmdb-movies2')
const showAllCredits = ref(false)
const aggregatedCredits = ref<any>(null)
const isLoadingAggregated = ref(false)

const showBatchAiModal = ref(false)
const batchAiLoading = ref(false)
const showSaveAllBtn = ref(false)
const batchAiOptions = reactive({ cast_name: true, cast_character: true, crew_name: false, crew_job: false })

// ── 批量编辑状态 ──
const showBatchEditModal = ref(false)
const editCastList = ref<any[]>([])
const editCrewList = ref<any[]>([])
const editTab = ref<'cast' | 'crew'>('cast')
const showAdvancedFields = ref(false)

const creditsData = computed(() => {
  const meta = store.itemDetails?.full_metadata
  if (!meta) return null
  if (meta.credits && (meta.credits.cast || meta.credits.crew)) return meta.credits
  if (meta.casts && (meta.casts.cast || meta.casts.crew)) return meta.casts
  return null
})

const displayedCredits = computed(() => {
  const base = creditsData.value || { cast: [], crew: [] }
  if (!showAllCredits.value || isMovie.value) return base
  return aggregatedCredits.value || base
})

watch(showAllCredits, async (val) => {
  if (val && !isMovie.value) {
    isLoadingAggregated.value = true
    aggregatedCredits.value = null
    try { aggregatedCredits.value = await getTvAggregatedCredits(store.currentItemId) }
    catch (e) { console.error('Failed to fetch aggregated credits', e) }
    finally { isLoadingAggregated.value = false }
  }
})

watch(() => store.currentItemId, () => { aggregatedCredits.value = null; showAllCredits.value = false })

function openActorDetail(person: any) {
  if (person.id) {
    router.push({ name: 'actorDetailByTmdbId', params: { tmdbId: String(person.id) } })
  }
}

async function runBatchAiTranslate() {
  if (!aiStore.config.enabled) { notify('提示', '请先开启 AI 服务', 'warning'); return }
  batchAiLoading.value = true
  try {
    const uniqueTexts: Record<string, Set<string>> = { cast_name: new Set(), cast_character: new Set(), crew_name: new Set(), crew_job: new Set() }
    const collectFromCredits = (credits: any) => {
      if (!credits) return
      const actors = [...(credits.cast || []), ...(credits.guest_stars || [])]
      actors.forEach((p: any) => {
        if (batchAiOptions.cast_name && p.name) uniqueTexts.cast_name.add(p.name)
        if (batchAiOptions.cast_character && p.character) p.character.split('/').forEach((c: string) => uniqueTexts.cast_character.add(c.trim()))
      })
      if (credits.crew) credits.crew.forEach((p: any) => { if (batchAiOptions.crew_name && p.name) uniqueTexts.crew_name.add(p.name); if (batchAiOptions.crew_job && p.job) uniqueTexts.crew_job.add(p.job) })
    }
    collectFromCredits(creditsData.value)
    if (!isMovie.value && store.itemDetails?.seasons) store.itemDetails.seasons.forEach((s: any) => { if (s.metadata) collectFromCredits(s.metadata.credits || s.metadata.casts); if (s.episodes) s.episodes.forEach((e: any) => collectFromCredits(e.metadata?.credits || e.metadata?.casts)) })
    const translationMap: Record<string, Map<string, string>> = { cast_name: new Map(), cast_character: new Map(), crew_name: new Map(), crew_job: new Map() }
    for (const context of Object.keys(uniqueTexts)) {
      const texts = Array.from(uniqueTexts[context])
      if (texts.length === 0) continue
      const meta = store.itemDetails?.full_metadata
      const extra_info = { item_name: meta?.name || meta?.title || store.itemDetails?.name, item_id: store.currentItemId, item_type: store.currentItemType, item_genres: meta?.genres?.map((g: any) => g.name).join(', '), original_language: meta?.original_language }
      const chunkSize = 15
      for (let i = 0; i < texts.length; i += chunkSize) {
        const chunk = texts.slice(i, i + chunkSize)
        notify('翻译中', `${context}: ${i + 1}/${texts.length}`, 'info')
        const res = await batchTranslationApi(chunk, context, extra_info)
        if (res.results) chunk.forEach((original, idx) => { if (res.results[idx]) { const clean = res.results[idx].replace(/^\d+[\.、\s]+/, '').trim(); translationMap[context].set(original, clean) } })
      }
    }
    const applyToCredits = (credits: any) => {
      if (!credits) return
      const actors = [...(credits.cast || []), ...(credits.guest_stars || [])]
      actors.forEach((p: any) => { if (translationMap.cast_name.has(p.name)) p.name = translationMap.cast_name.get(p.name); if (p.character) { const chars = p.character.split('/').map((c: string) => { const trimmed = c.trim(); return translationMap.cast_character.get(trimmed) || trimmed }); p.character = chars.join(' / ') } })
      if (credits.crew) credits.crew.forEach((p: any) => { if (translationMap.crew_name.has(p.name)) p.name = translationMap.crew_name.get(p.name); if (p.job && translationMap.crew_job.has(p.job)) p.job = translationMap.crew_job.get(p.job) })
    }
    applyToCredits(creditsData.value)
    if (!isMovie.value && store.itemDetails?.seasons) store.itemDetails.seasons.forEach((s: any) => { if (s.metadata) applyToCredits(s.metadata.credits || s.metadata.casts); if (s.episodes) s.episodes.forEach((e: any) => applyToCredits(e.metadata?.credits || e.metadata?.casts)) })
    notify('批量翻译完成', '请点击保存按钮', 'success')
    showSaveAllBtn.value = true
    showBatchAiModal.value = false
  } catch (e: any) { notify('批量翻译失败', e.message, 'error') }
  finally { batchAiLoading.value = false }
}

async function handleSaveAll() { const success = await store.saveAllChanges(); if (success) { notify('已保存', '', 'success'); showSaveAllBtn.value = false } else notify('保存失败', '', 'error') }

// ── 批量编辑功能 ──

function openBatchEdit() {
  const credits = creditsData.value
  editCastList.value = credits?.cast ? JSON.parse(JSON.stringify(credits.cast)) : []
  editCrewList.value = credits?.crew ? JSON.parse(JSON.stringify(credits.crew)) : []
  editTab.value = 'cast'
  showAdvancedFields.value = false
  showBatchEditModal.value = true
}

function addCastEntry() {
  editCastList.value.push({
    id: Date.now() + Math.random(),
    name: '',
    character: '',
    profile_path: '',
    original_name: '',
    order: editCastList.value.length,
  })
}

function addCrewEntry() {
  editCrewList.value.push({
    id: Date.now() + Math.random(),
    name: '',
    job: '',
    department: '',
    profile_path: '',
    original_name: '',
  })
}

function deleteCastEntry(index: number) {
  editCastList.value.splice(index, 1)
}

function deleteCrewEntry(index: number) {
  editCrewList.value.splice(index, 1)
}

function moveCast(index: number, direction: -1 | 1) {
  const newIndex = index + direction
  if (newIndex < 0 || newIndex >= editCastList.value.length) return
  const list = editCastList.value
  ;[list[index], list[newIndex]] = [list[newIndex], list[index]]
}

function moveCrew(index: number, direction: -1 | 1) {
  const newIndex = index + direction
  if (newIndex < 0 || newIndex >= editCrewList.value.length) return
  const list = editCrewList.value
  ;[list[index], list[newIndex]] = [list[newIndex], list[index]]
}

async function saveBatchEdit() {
  const meta = store.itemDetails?.full_metadata
  if (!meta) { notify('错误', '没有可编辑的元数据', 'error'); return }

  // 确定演职员数据存放的 key（credits 或 casts）
  let creditsObj: any = null
  if (meta.credits) {
    creditsObj = meta.credits
  } else if (meta.casts) {
    creditsObj = meta.casts
  } else {
    meta.credits = { cast: [], crew: [] }
    creditsObj = meta.credits
  }

  // 更新 cast 的 order 字段
  editCastList.value.forEach((p: any, i: number) => { p.order = i })

  creditsObj.cast = editCastList.value
  creditsObj.crew = editCrewList.value

  const success = await store.saveMetadata(meta)
  if (success) {
    notify('演职员信息已保存', '', 'success')
    showBatchEditModal.value = false
  } else {
    notify('保存失败', '', 'error')
  }
}
</script>

<template>
  <v-container fluid>
    <div class="d-flex flex-wrap align-center ga-2 mb-4">
      <v-btn v-if="showSaveAllBtn" color="error" size="small" variant="tonal" @click="handleSaveAll" :loading="store.isLoading" prepend-icon="mdi-content-save">保存更改</v-btn>
      <v-btn size="small" variant="tonal" color="warning" @click="openBatchEdit" prepend-icon="mdi-account-edit-outline">批量编辑</v-btn>
      <v-btn size="small" variant="tonal" color="primary" @click="showBatchAiModal = true" prepend-icon="mdi-translate">AI 批量中文化</v-btn>
      <v-checkbox v-if="!isMovie" v-model="showAllCredits" label="显示所有季/集演职员" density="compact" hide-details />
    </div>

    <div v-if="isLoadingAggregated" class="text-center pa-4">
      <v-progress-circular indeterminate color="primary" size="32" />
      <p class="mt-2 text-medium-emphasis">加载中...</p>
    </div>

    <template v-else-if="displayedCredits">
      <v-sheet v-if="displayedCredits.cast?.length" class="pa-4 mb-4" rounded border>
        <div class="d-flex align-center mb-3">
          <span class="text-subtitle-2 font-weight-bold">演员</span>
          <v-chip v-if="showAllCredits" size="x-small" variant="tonal" class="ml-2">{{ displayedCredits.cast.length }} 人</v-chip>
        </div>
        <div class="cast-card-grid">
          <v-card
            v-for="person in displayedCredits.cast.slice(0, showAllCredits ? 100 : 30)"
            :key="person.id"
            class="cc-wrapper poster-card"
            rounded="xl"
            variant="outlined"
            hover
            @click="openActorDetail(person)"
          >
            <!-- 演员图片 -->
            <div class="cc-poster-wrap poster-card__wrap">
              <v-img
                v-if="person.profile_path"
                :src="`/tmdb-mock/t/p/w342${person.profile_path}`"
                :alt="person.name"
                cover
                class="cc-poster-img poster-card__img"
              >
                <template #error>
                  <div class="cc-poster-placeholder">
                    <v-icon size="40">mdi-account</v-icon>
                  </div>
                </template>
              </v-img>
              <div v-else class="cc-poster-placeholder">
                <v-icon size="40">mdi-account</v-icon>
              </div>
            </div>
            <!-- 演员信息：名字 + 角色（配音） -->
            <div class="cc-info poster-card__info">
              <div class="cc-name text-truncate" :title="person.name">{{ person.name }}</div>
              <div v-if="person.character" class="cc-character text-truncate" :title="person.character">{{ person.character }}</div>
            </div>
          </v-card>
        </div>
      </v-sheet>

      <v-sheet v-if="displayedCredits.crew?.length" class="pa-4" rounded border>
        <div class="text-subtitle-2 font-weight-bold mb-3">制作人员</div>
        <v-row>
          <v-col v-for="person in displayedCredits.crew.slice(0, 30)" :key="`${person.id}-${person.job}`" cols="6" sm="4" md="3">
            <v-list-item link @click="openActorDetail(person)">
              <v-list-item-title class="text-truncate text-body-2">{{ person.name }}</v-list-item-title>
              <v-list-item-subtitle class="text-truncate text-caption">{{ person.job }}</v-list-item-subtitle>
            </v-list-item>
          </v-col>
        </v-row>
      </v-sheet>
    </template>

    <div v-else class="text-center pa-8 text-medium-emphasis">
      <v-icon size="48">mdi-account-off-outline</v-icon>
      <p class="mt-2">暂无演职员信息</p>
    </div>

    <v-dialog v-model="showBatchAiModal" max-width="420">
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-translate" class="mr-2" />AI 一键中文化
        </v-card-title>
        <v-card-text>
          <v-checkbox v-model="batchAiOptions.cast_name" label="翻译演员姓名" density="compact" hide-details />
          <v-checkbox v-model="batchAiOptions.cast_character" label="翻译角色名称" density="compact" hide-details />
          <v-divider class="my-2" />
          <v-checkbox v-model="batchAiOptions.crew_name" label="翻译制作人姓名" density="compact" hide-details />
          <v-checkbox v-model="batchAiOptions.crew_job" label="翻译职位名称" density="compact" hide-details />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showBatchAiModal = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-translate" :loading="batchAiLoading" @click="runBatchAiTranslate">开始处理</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 批量编辑弹框 -->
    <v-dialog v-model="showBatchEditModal" max-width="960" scrollable>
      <v-card rounded="xl">
        <v-card-title class="d-flex align-center">
          <v-icon icon="mdi-account-edit-outline" class="mr-2" />
          批量编辑演职员
          <v-spacer />
          <v-switch v-model="showAdvancedFields" label="高级字段" density="compact" hide-details color="primary" class="mr-2" />
          <v-btn icon="mdi-close" variant="text" size="small" @click="showBatchEditModal = false" />
        </v-card-title>
        <v-divider />
        <v-tabs v-model="editTab" density="compact" color="primary">
          <v-tab value="cast" prepend-icon="mdi-account">演员 ({{ editCastList.length }})</v-tab>
          <v-tab value="crew" prepend-icon="mdi-account-tie">制作人员 ({{ editCrewList.length }})</v-tab>
        </v-tabs>
        <v-divider />
        <v-card-text class="batch-edit-scroll">
          <v-window v-model="editTab">
            <!-- 演员 Tab -->
            <v-window-item value="cast">
              <div v-if="editCastList.length === 0" class="text-center text-medium-emphasis pa-4">
                <v-icon size="40">mdi-account-off-outline</v-icon>
                <p class="mt-2">暂无演员数据</p>
              </div>
              <div v-else class="d-flex flex-column ga-2">
                <div v-for="(person, index) in editCastList" :key="index" class="batch-edit-row pa-2">
                  <div class="d-flex align-center ga-2">
                    <v-avatar size="40" rounded class="flex-shrink-0">
                      <v-img v-if="person.profile_path" :src="`/tmdb-mock/t/p/w92${person.profile_path}`">
                        <template #error><v-icon>mdi-account</v-icon></template>
                      </v-img>
                      <v-icon v-else>mdi-account</v-icon>
                    </v-avatar>
                    <v-text-field v-model="person.name" label="姓名" density="compact" variant="outlined" hide-details class="flex-grow-1" />
                    <v-text-field v-model="person.character" label="角色名" density="compact" variant="outlined" hide-details class="flex-grow-1" />
                    <div class="d-flex flex-shrink-0">
                      <v-btn size="small" variant="text" icon="mdi-chevron-up" density="comfortable" :disabled="index === 0" @click="moveCast(index, -1)" />
                      <v-btn size="small" variant="text" icon="mdi-chevron-down" density="comfortable" :disabled="index === editCastList.length - 1" @click="moveCast(index, 1)" />
                      <v-btn size="small" variant="text" icon="mdi-delete-outline" color="error" density="comfortable" @click="deleteCastEntry(index)" />
                    </div>
                  </div>
                  <v-expand-transition>
                    <div v-show="showAdvancedFields" class="d-flex align-center ga-2 mt-2 pl-12">
                      <v-text-field v-model="person.original_name" label="原名" density="compact" variant="outlined" hide-details class="flex-grow-1" />
                      <v-text-field v-model="person.profile_path" label="头像路径 (profile_path)" density="compact" variant="outlined" hide-details class="flex-grow-1" />
                      <v-text-field v-model="person.id" label="TMDB ID" density="compact" variant="outlined" hide-details class="mw-120px" />
                    </div>
                  </v-expand-transition>
                </div>
              </div>
              <v-btn variant="tonal" color="primary" size="small" prepend-icon="mdi-plus" class="mt-3" @click="addCastEntry">添加演员</v-btn>
            </v-window-item>

            <!-- 制作人员 Tab -->
            <v-window-item value="crew">
              <div v-if="editCrewList.length === 0" class="text-center text-medium-emphasis pa-4">
                <v-icon size="40">mdi-account-tie-outline</v-icon>
                <p class="mt-2">暂无制作人员数据</p>
              </div>
              <div v-else class="d-flex flex-column ga-2">
                <div v-for="(person, index) in editCrewList" :key="index" class="batch-edit-row pa-2">
                  <div class="d-flex align-center ga-2">
                    <v-avatar size="40" rounded class="flex-shrink-0">
                      <v-img v-if="person.profile_path" :src="`/tmdb-mock/t/p/w92${person.profile_path}`">
                        <template #error><v-icon>mdi-account-tie</v-icon></template>
                      </v-img>
                      <v-icon v-else>mdi-account-tie</v-icon>
                    </v-avatar>
                    <v-text-field v-model="person.name" label="姓名" density="compact" variant="outlined" hide-details class="flex-grow-1" />
                    <v-text-field v-model="person.job" label="职位" density="compact" variant="outlined" hide-details class="flex-grow-1" />
                    <v-text-field v-model="person.department" label="部门" density="compact" variant="outlined" hide-details class="mw-140px" />
                    <div class="d-flex flex-shrink-0">
                      <v-btn size="small" variant="text" icon="mdi-chevron-up" density="comfortable" :disabled="index === 0" @click="moveCrew(index, -1)" />
                      <v-btn size="small" variant="text" icon="mdi-chevron-down" density="comfortable" :disabled="index === editCrewList.length - 1" @click="moveCrew(index, 1)" />
                      <v-btn size="small" variant="text" icon="mdi-delete-outline" color="error" density="comfortable" @click="deleteCrewEntry(index)" />
                    </div>
                  </div>
                  <v-expand-transition>
                    <div v-show="showAdvancedFields" class="d-flex align-center ga-2 mt-2 pl-12">
                      <v-text-field v-model="person.original_name" label="原名" density="compact" variant="outlined" hide-details class="flex-grow-1" />
                      <v-text-field v-model="person.profile_path" label="头像路径 (profile_path)" density="compact" variant="outlined" hide-details class="flex-grow-1" />
                      <v-text-field v-model="person.id" label="TMDB ID" density="compact" variant="outlined" hide-details class="mw-120px" />
                    </div>
                  </v-expand-transition>
                </div>
              </div>
              <v-btn variant="tonal" color="primary" size="small" prepend-icon="mdi-plus" class="mt-3" @click="addCrewEntry">添加制作人员</v-btn>
            </v-window-item>
          </v-window>
        </v-card-text>
        <v-divider />
        <v-card-actions>
          <span class="text-caption text-medium-emphasis ml-2">编辑后会直接保存到主条目元数据</span>
          <v-spacer />
          <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="showBatchEditModal = false">取消</v-btn>
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-content-save" @click="saveBatchEdit" :loading="store.isLoading">保存</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<style scoped>
/* 海报卡骨架（poster-card__*）由 cards.css 统一提供；此处保留演员卡的圆角穿透与排版差异 */
.cc-wrapper {
  cursor: pointer;
}

.cc-poster-wrap {
  /* 让图片四角同步裁切，与首页卡片一致 */
  border-radius: inherit;
}

.cc-poster-img {
  border-radius: inherit;
}
/* Vuetify v-img 内部的 <img> 是 absolute 定位，需要继承圆角才能裁切 */
.cc-poster-img :deep(.v-img__img) {
  border-radius: inherit;
}

.cc-poster-placeholder {
  width: 100%;
  aspect-ratio: 2 / 3;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgb(var(--v-theme-on-surface));
  border-radius: var(--am-surface-radius, 16px);
}

.cc-info {
  padding: 8px 8px 10px;
  text-align: center;
}
.cc-name {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
  color: rgb(var(--v-theme-on-surface));
}
.cc-character {
  font-size: 11px;
  line-height: 1.4;
  color: rgb(var(--v-theme-on-surface));
  margin-top: 2px;
}

/* ── 批量编辑弹框 ── */
.batch-edit-scroll {
  max-height: 60vh;
}

.batch-edit-row {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: var(--am-list-item-radius, 12px);
  transition: border-color 0.2s;
}
.batch-edit-row:hover {
  border-color: rgba(var(--v-theme-primary), 0.5);
}
</style>

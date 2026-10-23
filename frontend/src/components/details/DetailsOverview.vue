<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDetailsStore } from '@/stores'
import { getExternalIds } from '@/api/details'

const store = useDetailsStore()

const isMovie = computed(() => store.currentItemType === 'tmdb-movies2')

const externalIdsData = ref<any>(null)
const mainExternalIds = computed(() => externalIdsData.value?.external_ids || {})
const sortedSeasonsExternalIds = computed(() => {
  if (!externalIdsData.value?.seasons) return []
  return [...externalIdsData.value.seasons].sort((a: any, b: any) => a.season_number - b.season_number)
})
const hasExternalIds = computed(() => {
  if (!externalIdsData.value) return false
  const mainKeys = Object.keys(mainExternalIds.value).filter(k => mainExternalIds.value[k])
  return mainKeys.length > 0 || sortedSeasonsExternalIds.value.length > 0
})

function parseBgmIds(bgmId: string | undefined): string[] {
  if (!bgmId) return []
  return bgmId.split(',').map(id => id.trim()).filter(Boolean)
}

async function loadExternalIds() {
  if (!store.currentItemId) return
  try {
    externalIdsData.value = await getExternalIds(store.currentItemType, store.currentItemId)
  } catch (e) { externalIdsData.value = null }
}

watch(() => store.itemDetails, () => {
  loadExternalIds()
}, { deep: true, immediate: true })
</script>

<template>
  <v-container fluid class="pa-0">
    <!-- 本地标签 -->
    <v-sheet v-if="store.itemDetails?.tags?.length" class="pa-4 mb-4" rounded="xl" border>
      <div class="text-subtitle-2 font-weight-bold mb-2">本地标签</div>
      <div class="d-flex flex-wrap ga-1">
        <v-chip v-for="tag in store.itemDetails.tags" :key="tag" size="small" variant="tonal" label>{{ tag }}</v-chip>
      </div>
    </v-sheet>

    <!-- 外部链接 -->
    <v-sheet v-if="hasExternalIds" class="pa-4 mb-4" rounded="xl" border>
      <div class="text-subtitle-2 font-weight-bold mb-2">外部链接</div>
      <div class="d-flex flex-wrap ga-2 mb-2">
        <v-btn v-if="mainExternalIds.imdb_id" size="small" variant="tonal" color="info" :href="`https://www.imdb.com/title/${mainExternalIds.imdb_id}`" target="_blank" prepend-icon="mdi-open-in-new">IMDB</v-btn>
        <v-btn v-if="mainExternalIds.tvdb_id" size="small" variant="tonal" color="info" :href="`https://thetvdb.com/?tab=series&id=${mainExternalIds.tvdb_id}`" target="_blank" prepend-icon="mdi-open-in-new">TVDB</v-btn>
        <v-btn v-if="mainExternalIds.douban_id" size="small" variant="tonal" color="success" :href="`https://movie.douban.com/subject/${mainExternalIds.douban_id}/`" target="_blank" prepend-icon="mdi-open-in-new">豆瓣</v-btn>
        <template v-if="mainExternalIds.bgm_id">
          <v-btn v-for="bgmId in parseBgmIds(mainExternalIds.bgm_id)" :key="bgmId" size="small" variant="tonal" color="warning" :href="`https://bgm.tv/subject/${bgmId}`" target="_blank" prepend-icon="mdi-open-in-new">BGM {{ bgmId }}</v-btn>
        </template>
      </div>
      <v-expansion-panels v-if="!isMovie && sortedSeasonsExternalIds.length" variant="accordion">
        <v-expansion-panel v-for="season in sortedSeasonsExternalIds" :key="season.season_number" :title="`第 ${season.season_number} 季外部链接`">
          <v-expansion-panel-text>
            <div class="d-flex flex-wrap ga-2">
              <v-btn v-if="season.external_ids.imdb_id" size="x-small" variant="tonal" color="info" :href="`https://www.imdb.com/title/${season.external_ids.imdb_id}`" target="_blank">IMDB: {{ season.external_ids.imdb_id }}</v-btn>
              <v-btn v-if="season.external_ids.tvdb_id" size="x-small" variant="tonal" color="info" :href="`https://thetvdb.com/?tab=series&id=${season.external_ids.tvdb_id}`" target="_blank">TVDB: {{ season.external_ids.tvdb_id }}</v-btn>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </v-sheet>
  </v-container>
</template>

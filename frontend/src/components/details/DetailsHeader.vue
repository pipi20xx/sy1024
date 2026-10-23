<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useDetailsStore } from '@/stores'

const store = useDetailsStore()
const router = useRouter()

const isMovie = computed(() => store.currentItemType === 'tmdb-movies2')

const displayTitle = computed(() => {
  const d = store.itemDetails
  if (!d) return ''
  const meta = d.full_metadata
  return d.name || d.title || meta?.name || meta?.title || '未知'
})

const originalTitle = computed(() => {
  const meta = store.itemDetails?.full_metadata
  if (!meta) return (store.itemDetails as any)?.original_name || ''
  return meta[isMovie.value ? 'original_title' : 'original_name'] || ''
})

const posterUrl = computed(() => {
  if (store.itemDetails?.images?.length) {
    const poster = store.itemDetails.images.find((img: any) => img.label === '海报' || img.name?.includes('poster'))
    if (poster) return poster.url
  }
  return store.itemDetails?.poster_path || '/static/placeholder.png'
})

const statusText = computed(() => {
  const s = store.itemDetails?.full_metadata?.status
  if (!s) return ''
  const map: Record<string, string> = {
    'Ended': '已完结', 'Returning Series': '连载中', 'Canceled': '已取消',
    'In Production': '制作中', 'Planned': '计划中', 'Released': '已上映',
    'Post Production': '后期制作', 'Rumored': '传闻', 'Pilot': '试播集',
  }
  return map[s] || s
})

const voteAverage = computed(() => store.itemDetails?.full_metadata?.vote_average)

const genres = computed(() => {
  const g = store.itemDetails?.full_metadata?.genres
  if (!g) return []
  return g.map((x: any) => x.name || x)
})

const belongsToCollections = computed(() => {
  const c = store.itemDetails?.full_metadata?.belongs_to_collections
  if (!Array.isArray(c)) return []
  return c as { collection_name: string; filename: string; poster_path?: string }[]
})

const tagline = computed(() => store.itemDetails?.full_metadata?.tagline)

const overview = computed(() => store.itemDetails?.full_metadata?.overview)

const airDate = computed(() => {
  const meta = store.itemDetails?.full_metadata
  if (!meta) return ''
  const d = meta.release_date || meta.first_air_date || ''
  return d && d.length >= 10 ? d.substring(0, 10) : (d || '')
})

const lastAirDate = computed(() => {
  if (isMovie.value) return ''
  const d = store.itemDetails?.full_metadata?.last_air_date
  return d && d.length >= 10 ? d.substring(0, 10) : (d || '')
})

function goToCollection(filename: string) {
  router.push({ name: 'collectionDetail', params: { filename } })
}
</script>

<template>
  <v-container v-if="store.itemDetails" fluid class="pa-0">
    <v-row>
      <!-- 海报 -->
      <v-col cols="4" sm="3" md="2">
        <v-img
          :src="posterUrl"
          aspect-ratio="2/3"
          cover
          rounded="xl"
        >
          <template #error>
            <v-sheet class="d-flex align-center justify-center fill-height rounded-xl">
              <v-icon size="40" color="grey">mdi-filmstrip</v-icon>
            </v-sheet>
          </template>
        </v-img>
      </v-col>

      <!-- 信息区 -->
      <v-col cols="8" sm="9" md="10">
        <!-- 标题 -->
        <h2 class="text-h5 font-weight-bold text-truncate">{{ displayTitle }}</h2>
        <p v-if="originalTitle && originalTitle !== displayTitle" class="text-body-2 text-medium-emphasis text-truncate mt-1">
          {{ originalTitle }}
        </p>

        <!-- 核心标签行：状态 / 评分 / 日期 -->
        <div class="d-flex flex-wrap ga-1 mt-3">
          <v-chip v-if="statusText" size="small" variant="tonal" color="success">
            <v-icon start size="x-small">mdi-circle-slice-8</v-icon>{{ statusText }}
          </v-chip>
          <v-chip v-if="voteAverage" size="small" variant="tonal" color="warning">
            <v-icon start size="x-small">mdi-star</v-icon>{{ voteAverage.toFixed(1) }}
          </v-chip>
          <v-chip v-if="airDate" size="small" variant="tonal" label>
            <v-icon start size="x-small">mdi-calendar</v-icon>{{ isMovie ? '上映' : '首播' }} {{ airDate }}
          </v-chip>
          <v-chip v-if="lastAirDate" size="small" variant="tonal" label>
            <v-icon start size="x-small">mdi-calendar-check</v-icon>完结 {{ lastAirDate }}
          </v-chip>
        </div>

        <!-- 类型标签 -->
        <div v-if="genres.length" class="d-flex flex-wrap ga-1 mt-3">
          <v-chip v-for="g in genres" :key="g" size="x-small" variant="outlined" label>{{ g }}</v-chip>
        </div>

        <!-- 所属合集 -->
        <div v-if="belongsToCollections.length" class="d-flex flex-wrap ga-1 mt-3">
          <v-chip
            v-for="col in belongsToCollections"
            :key="col.filename"
            size="small"
            variant="tonal"
            color="info"
            link
            @click="goToCollection(col.filename)"
          >
            <v-icon start size="x-small">mdi-folder-multiple-outline</v-icon>
            {{ col.collection_name }}
          </v-chip>
        </div>

        <!-- 宣传语 -->
        <p v-if="tagline" class="text-body-2 font-italic text-medium-emphasis mt-3">
          "{{ tagline }}"
        </p>

        <!-- 简介 -->
        <p v-if="overview" class="line-clamp-4 text-body-2 mt-3">
          {{ overview }}
        </p>

        <!-- 剧集组视图切换 -->
        <div class="d-flex ga-2 mt-3">
          <v-btn
            v-if="!isMovie && store.itemDetails.override_episodegroup_exists"
            size="x-small"
            variant="tonal"
            :color="store.currentViewMode === 'episodegroup' ? 'primary' : 'default'"
            @click="store.toggleViewMode()"
          >
            {{ store.currentViewMode === 'episodegroup' ? '标准视图' : '剧集组视图' }}
          </v-btn>
        </div>
      </v-col>
    </v-row>
  </v-container>
</template>

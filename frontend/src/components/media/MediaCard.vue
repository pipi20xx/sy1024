<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { ItemSummary } from '@/types'

const props = defineProps<{ item: ItemSummary }>()
const router = useRouter()

const posterUrl = computed(() => props.item.poster_path || '/static/placeholder.png')
const title = computed(() => props.item.name || props.item.title || '未知标题')
const year = computed(() => props.item.year ? `(${props.item.year})` : '')

function handleClick() {
  const route = router.resolve({ name: 'itemDetail', params: { itemType: props.item.type, tmdbId: props.item.id } })
  if (localStorage.getItem('open_detail_in_new_tab') === 'true') {
    window.open(route.href, '_blank')
  } else {
    router.push(route)
  }
}
</script>

<template>
  <v-card
    hover
    rounded="xl"
    variant="outlined"
    class="media-liquid-card poster-card"
    @click="handleClick"
  >
    <!-- 海报图 -->
    <div class="poster-card__wrap">
      <v-img :src="posterUrl" :alt="title" cover class="poster-card__img poster-rounded">
        <template #error>
          <div class="d-flex align-center justify-center fill-height bg-surface-variant">
            <v-icon size="48" color="grey-lighten-1">mdi-image-off-outline</v-icon>
          </div>
        </template>
      </v-img>
      <!-- 入库状态角标 -->
      <v-chip
        v-if="item.in_library !== undefined"
        size="x-small"
        :color="item.in_library ? 'success' : 'error'"
        variant="flat"
        density="compact"
        class="poster-badge position-absolute corner-badge corner-badge--tr"
      >
        <v-icon start size="x-small">{{ item.in_library ? 'mdi-check-circle' : 'mdi-close-circle' }}</v-icon>
        {{ item.in_library ? '已入库' : '未入库' }}
      </v-chip>
      <!-- BGM 映射状态角标 -->
      <v-chip
        v-if="item.has_bgm_mapping !== undefined"
        size="x-small"
        color="pink"
        variant="flat"
        density="compact"
        class="poster-badge position-absolute corner-badge corner-badge--bl"
      >
        <v-icon start size="x-small">mdi-link-variant</v-icon>
        {{ item.has_bgm_mapping ? 'BGM' : '无BGM' }}
      </v-chip>
    </div>

    <!-- 底部信息 -->
    <div class="poster-card__info mc-info">
      <div class="text-body-2 font-weight-bold text-center text-truncate" :title="title">{{ title }}</div>
      <div v-if="year" class="text-caption text-medium-emphasis mt-1 text-center">{{ year }}</div>
      <!-- 类型标签 -->
      <div v-if="item.genres?.length" class="d-flex flex-wrap ga-1 mt-2 justify-center">
        <v-chip
          v-for="genre in item.genres.slice(0, 2)"
          :key="genre"
          size="x-small"
          variant="tonal"
          label
          density="comfortable"
        >
          {{ genre }}
        </v-chip>
        <v-chip v-if="item.genres.length > 2" size="x-small" variant="tonal" label density="comfortable">
          +{{ item.genres.length - 2 }}
        </v-chip>
      </div>
    </div>
  </v-card>
</template>

<style scoped>
/* 海报卡骨架（poster-card__*）与海报圆角（poster-rounded）由 cards.css / utilities.css 统一提供 */
.mc-info {
  padding: 12px;
}
</style>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
defineOptions({ name: 'BangumiView' })
import { getBangumiDataVersionApi } from '@/api/bangumi'
import BangumiEmbySyncTab from '@/components/bangumi/BangumiEmbySyncTab.vue'

// ==================== bangumi-data 映射表版本 ====================
const bangumiDataVersion = ref('')

// ==================== 生命周期 ====================
onMounted(() => {
  loadBangumiDataVersion()
})

// ==================== bangumi-data 映射表版本加载 ====================
async function loadBangumiDataVersion() {
  try {
    const data = await getBangumiDataVersionApi()
    bangumiDataVersion.value = data.version || ''
  } catch (e) {
    console.error('Failed to load bangumi-data version:', e)
  }
}
</script>

<template>
  <v-container fluid class="pa-6">
    <!-- 页面标题 -->
    <div class="d-flex flex-wrap align-center mb-6 ga-3">
      <div class="flex-grow-1">
        <h1 class="text-h5 font-weight-bold">Bangumi 映射管理</h1>
        <p class="text-caption text-medium-emphasis mt-1">管理 bangumi-data 映射表同步与元数据写入</p>
      </div>
    </div>

    <!-- bangumi-data 映射表版本信息 -->
    <v-card variant="outlined" rounded="xl" class="mb-4">
      <v-card-title class="text-subtitle-2 font-weight-bold pa-4 pb-0">
        <v-icon start size="small">mdi-database-sync</v-icon>
        bangumi-data 映射表
      </v-card-title>

      <v-card-text class="pa-4">
        <div class="d-flex flex-wrap align-center ga-2">
          <v-chip v-if="bangumiDataVersion" color="success" size="small" variant="tonal">
            <v-icon start size="x-small">mdi-check-circle</v-icon>
            映射表版本: {{ bangumiDataVersion }}
          </v-chip>
          <v-chip v-else color="warning" size="small" variant="tonal">
            <v-icon start size="x-small">mdi-alert-circle</v-icon>
            映射表: 未同步
          </v-chip>
        </div>
        <p class="text-caption text-medium-emphasis mt-2">
          数据同步请在 <router-link to="/tasks" class="text-primary">定时任务</router-link> 中配置和管理
        </p>
      </v-card-text>
    </v-card>

    <!-- 元数据同步 (写入 Emby) -->
    <v-card variant="outlined" rounded="xl" class="mb-4">
      <v-card-title class="text-subtitle-2 font-weight-bold pa-4 pb-0">
        <v-icon start size="small">mdi-tag-multiple-outline</v-icon>
        元数据同步 (写入 Emby)
      </v-card-title>
      <v-card-text class="pa-4">
        <BangumiEmbySyncTab />
      </v-card-text>
    </v-card>
  </v-container>
</template>

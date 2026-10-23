<script setup lang="ts">
import { ref } from 'vue'
import { useCollectionStore } from '@/stores'
import { useNotification } from '@/composables'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const store = useCollectionStore()
const { notify } = useNotification()

const isProcessing = ref(false)

async function startApply() {
  isProcessing.value = true
  try {
    await store.applyAllToEmbyBg()
    notify('应用任务已在后台启动', '请查看顶部进度条', 'success')
    emit('update:modelValue', false)
  } catch (e: any) {
    notify('启动失败', e.message || '未知错误', 'error')
  } finally {
    isProcessing.value = false
  }
}

function handleClose() {
  if (isProcessing.value) return
  emit('update:modelValue', false)
}
</script>

<template>
  <v-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" max-width="560" scrollable>
    <v-card rounded="xl">
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-cloud-upload" class="mr-2" />
        应用所有合集到 Emby
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="handleClose" />
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-4">
        <p class="text-body-2 mb-3">
          此操作将遍历所有本地合集文件，并确保 Emby 服务器上的同名合集与本地文件内容<strong>完全一致</strong>。
        </p>

        <v-sheet variant="outlined" rounded="xl" class="pa-4 mb-3">
          <div class="text-subtitle-2 font-weight-bold mb-2">包括：</div>
          <ul class="text-body-2 ml-4 disc-list">
            <li>添加 Emby 合集中缺失的电影/剧集</li>
            <li>移除 Emby 合集中多余的电影/剧集</li>
            <li>上传封面和背景图</li>
          </ul>
        </v-sheet>

        <v-alert type="warning" variant="tonal" density="compact">
          请确保您已备份数据。
        </v-alert>
      </v-card-text>

      <v-divider />
      <v-card-actions class="pa-4">
        <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="handleClose" :disabled="isProcessing">取消</v-btn>
        <v-spacer />
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-check" :loading="isProcessing" @click="startApply">开始应用</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
/* 实心圆点列表（Vuetify 重置会去掉 ul 默认样式） */
.disc-list {
  list-style-type: disc;
}
</style>

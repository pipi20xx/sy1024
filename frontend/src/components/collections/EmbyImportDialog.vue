<script setup lang="ts">
import { ref } from 'vue'
import { useCollectionStore } from '@/stores'
import { useNotification } from '@/composables'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean]; refresh: [] }>()

const store = useCollectionStore()
const { notify } = useNotification()

const mode = ref<'single' | 'all'>('single')
const collectionName = ref('')
const overwriteJson = ref(false)
const overwriteImages = ref(false)
const isProcessing = ref(false)

async function handleImport() {
  if (mode.value === 'single' && !collectionName.value.trim()) {
    notify('提示', '请输入合集名称', 'warning')
    return
  }

  isProcessing.value = true
  try {
    if (mode.value === 'single') {
      await store.importFromEmby(collectionName.value, overwriteJson.value, overwriteImages.value)
      notify('导入成功', '', 'success')
    } else {
      await store.importAllFromEmby(overwriteJson.value, overwriteImages.value)
      notify('批量导入已在后台开始', '', 'success')
    }
    emit('refresh')
    emit('update:modelValue', false)
  } catch (e: any) {
    notify('导入失败', e.message || '未知错误', 'error')
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
        <v-icon icon="mdi-download" class="mr-2" />
        从 Emby 导入合集
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="handleClose" />
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-4">
        <!-- 模式选择 -->
        <div class="text-subtitle-2 font-weight-bold mb-2">导入模式</div>
        <v-radio-group v-model="mode" density="compact" hide-details class="mb-4">
          <v-radio label="导入单个合集" value="single" />
          <v-radio label="批量导入所有合集" value="all" />
        </v-radio-group>

        <!-- 单个输入 -->
        <v-text-field
          v-if="mode === 'single'"
          v-model="collectionName"
          label="Emby 中的合集名称"
          placeholder="例如: Marvel Universe"
          density="compact"
          variant="outlined"
          class="mb-4"
        />

        <!-- 导入策略 -->
        <v-sheet variant="outlined" rounded="xl" class="pa-4">
          <div class="text-subtitle-2 font-weight-bold mb-3">导入策略</div>
          <v-checkbox v-model="overwriteJson" density="compact" hide-details class="mb-2">
            <template #label>
              覆盖已存在的 JSON 文件
              <span class="text-caption text-medium-emphasis ml-2">(使用 Emby 数据强制更新本地文件)</span>
            </template>
          </v-checkbox>
          <v-checkbox v-model="overwriteImages" density="compact" hide-details>
            <template #label>
              覆盖已存在的图片文件
              <span class="text-caption text-medium-emphasis ml-2">(重新下载封面和背景图)</span>
            </template>
          </v-checkbox>
        </v-sheet>
      </v-card-text>

      <v-divider />
      <v-card-actions class="pa-4">
        <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="handleClose" :disabled="isProcessing">取消</v-btn>
        <v-spacer />
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-import" :loading="isProcessing" @click="handleImport">开始导入</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

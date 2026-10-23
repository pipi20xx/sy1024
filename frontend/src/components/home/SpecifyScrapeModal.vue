<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { embyApi } from '@/api/emby'
import { useNotification } from '@/composables'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const { notify } = useNotification()

const isVisible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const loading = ref(false)
const embyItemId = ref('')
const newTmdbId = ref('')

watch(() => props.modelValue, async (newVal) => {
  if (newVal) {
    newTmdbId.value = ''
    try {
      const data = await embyApi.getLastEmbyId()
      if (data?.emby_item_id) {
        embyItemId.value = data.emby_item_id
      }
    } catch {
      // 静默失败，用户可以手动输入
    }
  }
})

async function handleSubmit() {
  if (!embyItemId.value.trim()) {
    notify('提示', '请输入 Emby Item ID', 'warning')
    return
  }
  if (!newTmdbId.value.trim() || !/^\d+$/.test(newTmdbId.value.trim())) {
    notify('提示', 'TMDB ID 必须是纯数字', 'warning')
    return
  }

  loading.value = true
  try {
    await embyApi.specifyScrape({
      emby_item_id: embyItemId.value.trim(),
      new_tmdb_id: newTmdbId.value.trim(),
    })
    await embyApi.saveLastEmbyId({ emby_item_id: embyItemId.value.trim() })
    notify('指定刮削成功', '请求已发送', 'success')
    isVisible.value = false
  } catch (e: any) {
    notify('刮削失败', e.message, 'error')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <v-dialog v-model="isVisible" max-width="500" scrollable>
    <v-card rounded="xl">
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-target-account" class="mr-2" />
        指定刮削
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="isVisible = false" />
      </v-card-title>
      <v-divider />

      <v-card-text class="pt-4">
        <v-text-field v-model="embyItemId" label="Emby Item ID" density="compact" variant="outlined"
          placeholder="输入 Emby 中的 Item ID" class="mb-3" />
        <v-text-field v-model="newTmdbId" label="目标 TMDB ID" density="compact" variant="outlined"
          placeholder="输入新的 TMDB ID (纯数字)" hint="该 Emby 项目将重新关联到指定的 TMDB 条目"
          persistent-hint />
      </v-card-text>

      <v-divider />
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="isVisible = false">取消</v-btn>
        <v-btn color="primary" variant="tonal" :loading="loading" prepend-icon="mdi-send" @click="handleSubmit">
          提交
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

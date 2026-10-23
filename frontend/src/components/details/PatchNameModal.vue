<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDetailsStore } from '@/stores'
import { useNotification } from '@/composables'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()

const store = useDetailsStore()
const { notify } = useNotification()

const isMovie = computed(() => store.currentItemType === 'tmdb-movies2')
const nameField = computed(() => isMovie.value ? 'title' : 'name')
const nameLabel = computed(() => isMovie.value ? '电影标题' : '剧集标题')

const editingName = ref('')

watch(() => props.modelValue, (open) => {
  if (open) {
    const meta = store.itemDetails?.full_metadata
    editingName.value = meta?.[nameField.value] || ''
  }
})

async function handleSave() {
  const name = editingName.value.trim()
  if (!name) { notify('提示', '名称不能为空', 'warning'); return }
  emit('update:modelValue', false)
  const success = await store.updatePatchNameField(name)
  if (success) notify('保存成功', '', 'success')
  else notify('保存失败', '', 'error')
}
</script>

<template>
  <v-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" max-width="500">
    <v-card rounded="xl">
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-file-document-edit" class="mr-2" />
        编辑 Patches 名称
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="emit('update:modelValue', false)" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pt-4">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          修改将直接写入 Patches 文件，优先级高于 Override 和 Primary。
        </v-alert>
        <v-text-field
          v-model="editingName"
          :label="nameLabel"
          density="compact"
          variant="outlined"
          autofocus
          hide-details
          @keyup.enter="handleSave"
        />
      </v-card-text>
      <v-divider />
      <v-card-actions>
        <v-spacer />
        <v-btn type="button" variant="tonal" color="grey" prepend-icon="mdi-close" @click="emit('update:modelValue', false)">取消</v-btn>
        <v-btn type="button" color="primary" variant="tonal" prepend-icon="mdi-check" @click="handleSave" :loading="store.isLoading">保存</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

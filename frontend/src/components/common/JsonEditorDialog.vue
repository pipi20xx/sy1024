<script setup lang="ts">
import { ref, watch } from 'vue'
import { useNotification } from '@/composables'

const props = withDefaults(defineProps<{
  modelValue: boolean
  initialData: any
  title?: string
  confirmText?: string
  hint?: string
  loading?: boolean
}>(), {
  title: '编辑原始 JSON',
  confirmText: '保存',
  hint: '',
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [boolean]
  confirm: [any]
}>()

const { notify } = useNotification()
const jsonText = ref('')

watch(() => props.modelValue, (val) => {
  if (val) jsonText.value = JSON.stringify(props.initialData ?? {}, null, 2)
})

function close() {
  emit('update:modelValue', false)
}

function handleConfirm() {
  let parsed: any
  try {
    parsed = JSON.parse(jsonText.value)
  } catch {
    notify('JSON 格式错误', '请检查语法后重试', 'error')
    return
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    notify('JSON 格式错误', '顶层必须是一个 JSON 对象', 'error')
    return
  }
  emit('confirm', parsed)
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    @update:model-value="$emit('update:modelValue', $event)"
    max-width="800"
    scrollable
  >
    <v-card rounded="xl">
      <v-card-title class="d-flex align-center">
        <v-icon icon="mdi-code-block-braces" class="mr-2" />
        {{ title }}
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="close" />
      </v-card-title>
      <v-divider />
      <v-card-text>
        <div v-if="hint" class="text-caption text-medium-emphasis mb-2">{{ hint }}</div>
        <v-textarea
          v-model="jsonText"
          auto-grow
          variant="outlined"
          density="compact"
          rows="12"
          class="font-mono"
          hide-details
        />
      </v-card-text>
      <v-divider />
      <v-card-actions>
        <v-spacer />
        <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="close">取消</v-btn>
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-content-save" :loading="loading" @click="handleConfirm">{{ confirmText }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

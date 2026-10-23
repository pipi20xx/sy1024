<script setup lang="ts">
/**
 * GlassDialog — 全局统一的弹窗基础组件
 *
 * 封装了 Liquid Glass 风格的 v-dialog + v-card 结构，
 * 统一标题栏、分割线、内容区、操作栏的样式与行为。
 *
 * - scrollable=true（默认）：内容超出时由弹窗统一滚动，v-card-text 无独立滚动条
 * - scrollable=false：弹窗不滚动，适合内含 textarea 等自带滚动的场景
 * - 默认提供取消按钮，可通过 actions 插槽自定义额外按钮
 */
const props = withDefaults(defineProps<{
  modelValue: boolean
  maxWidth?: string | number
  title?: string
  icon?: string
  scrollable?: boolean
  cancelText?: string
  cancelVisible?: boolean
}>(), {
  maxWidth: 600,
  scrollable: true,
  cancelText: '取消',
  cancelVisible: true,
})

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  cancel: []
  dismiss: []
}>()

function handleCancel() {
  emit('cancel')
  emit('update:modelValue', false)
}

function handleDismiss() {
  emit('dismiss')
  emit('update:modelValue', false)
}
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    :max-width="maxWidth"
    :scrollable="scrollable"
  >
    <v-card class="liquid-glass-card">
      <!-- 标题栏 -->
      <v-card-title v-if="title || $slots.title" class="pa-4 d-flex align-center">
        <v-icon v-if="icon" start>{{ icon }}</v-icon>
        <slot name="title">{{ title }}</slot>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="handleDismiss" />
      </v-card-title>

      <v-divider v-if="title || $slots.title" />

      <!-- 内容区 -->
      <v-card-text class="pa-4">
        <slot />
      </v-card-text>

      <!-- 操作栏 -->
      <template v-if="$slots.actions || cancelVisible">
        <v-divider />
        <div class="d-flex justify-end ga-2 pa-4">
          <v-btn
            v-if="cancelVisible"
            variant="tonal"
            color="grey"
            prepend-icon="mdi-close"
            @click="handleCancel"
          >
            {{ cancelText }}
          </v-btn>
          <slot name="actions" />
        </div>
      </template>
    </v-card>
  </v-dialog>
</template>

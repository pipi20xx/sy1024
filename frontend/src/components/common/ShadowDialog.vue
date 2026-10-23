<script setup lang="ts">
/**
 * ShadowDialog — 阴影切换对话框
 *
 * 参考 BorderRadiusDialog 的结构，提供 5 种阴影预设。
 * 切换后立即生效并持久化，不受白天/夜晚模式影响。
 */
import { computed, ref, watch } from 'vue'
import { useThemeCustomizer, type ThemeCustomizerShadow } from '@/composables/useThemeCustomizer'
import { useDisplay } from 'vuetify'

const props = withDefaults(
  defineProps<{
    modelValue?: boolean
  }>(),
  {
    modelValue: true,
  },
)

const emit = defineEmits<{
  (event: 'close'): void
  (event: 'update:modelValue', value: boolean): void
}>()

const display = useDisplay()
const { settings, setShadow } = useThemeCustomizer()

const currentShadow = computed(() => settings.value.shadow)

const visible = computed({
  get: () => props.modelValue,
  set: (value) => {
    emit('update:modelValue', value)
    if (!value) emit('close')
  },
})

interface ShadowOption {
  value: ThemeCustomizerShadow
  label: string
  hint: string
  icon: string
  /** 预览方块的阴影 CSS */
  previewShadow: string
}

const shadowOptions: ShadowOption[] = [
  {
    value: 'none',
    label: '无阴影',
    hint: '所有组件无投影',
    icon: 'mdi-square-outline',
    previewShadow: 'none',
  },
  {
    value: 'subtle',
    label: '轻微',
    hint: '极淡投影，几乎不可见',
    icon: 'mdi-square-rounded-outline',
    previewShadow: '0 1px 3px rgba(0, 0, 0, 0.08)',
  },
  {
    value: 'default',
    label: '默认',
    hint: '保持各主题原生阴影',
    icon: 'mdi-square-rounded',
    previewShadow: '0 2px 8px rgba(0, 0, 0, 0.12)',
  },
  {
    value: 'prominent',
    label: '明显',
    hint: '清晰的深度层次感',
    icon: 'mdi-square-rounded',
    previewShadow: '0 6px 18px rgba(0, 0, 0, 0.22)',
  },
  {
    value: 'dramatic',
    label: '夸张',
    hint: '强烈的悬浮投影效果',
    icon: 'mdi-cube-outline',
    previewShadow: '0 12px 32px rgba(0, 0, 0, 0.35)',
  },
]

/** 用于自定义滑块的映射（0=none, 1=subtle, 2=default, 3=prominent, 4=dramatic） */
const shadowSliderValue = ref(2)

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      const idx = shadowOptions.findIndex(o => o.value === currentShadow.value)
      shadowSliderValue.value = idx >= 0 ? idx : 2
    }
  },
  { immediate: true },
)

function selectShadow(value: ThemeCustomizerShadow) {
  setShadow(value)
  const idx = shadowOptions.findIndex(o => o.value === value)
  if (idx >= 0) shadowSliderValue.value = idx
}

function onSliderChange(value: number) {
  const option = shadowOptions[value]
  if (option) selectShadow(option.value)
}

const currentOption = computed(() => shadowOptions.find(o => o.value === currentShadow.value) ?? shadowOptions[2])
</script>

<template>
  <VDialog
    v-model="visible"
    width="100%"
    max-width="32rem"
    scrollable
    :fullscreen="display.smAndDown.value"
  >
    <VCard>
      <VCardTitle class="d-flex align-center pa-4">
        <VIcon icon="mdi-box-shadow" class="me-2" />
        阴影
        <VSpacer />
        <VBtn
          icon
          variant="text"
          size="small"
          aria-label="关闭"
          @click.stop="visible = false"
        >
          <VIcon icon="mdi-close" />
        </VBtn>
      </VCardTitle>
      <VDivider />

      <VCardText class="appearance-dialog__body">
        <!-- 预设选项 -->
        <section>
          <h3 class="appearance-dialog__label">阴影强度</h3>
          <div class="appearance-dialog__grid">
            <button
              v-for="option in shadowOptions"
              :key="option.value"
              type="button"
              class="appearance-dialog__option"
              :class="{ 'appearance-dialog__option--active': currentShadow === option.value }"
              @click="selectShadow(option.value)"
            >
              <div
                class="appearance-dialog__preview"
                :style="{ boxShadow: option.previewShadow }"
              >
                <VIcon :icon="option.icon" size="20" />
              </div>
              <span class="appearance-dialog__option-label">{{ option.label }}</span>
            </button>
          </div>
          <p class="appearance-dialog__hint">
            点击预设即可切换阴影强度。阴影设置不会因深色/浅色模式切换而改变。
          </p>
        </section>

        <!-- 滑块调整 -->
        <section>
          <div class="appearance-dialog__slider-header">
            <h3 class="appearance-dialog__label">快速调整</h3>
            <span class="appearance-dialog__current-value">{{ currentOption.label }}</span>
          </div>
          <div class="appearance-dialog__slider-wrapper">
            <VSlider
              v-model="shadowSliderValue"
              :min="0"
              :max="4"
              :step="1"
              color="primary"
              show-ticks
              thumb-label
              @update:model-value="onSliderChange"
            >
              <template #thumb-label="{ modelValue }">
                {{ shadowOptions[modelValue]?.label ?? '' }}
              </template>
            </VSlider>
          </div>
          <div class="appearance-dialog__tick-labels">
            <span
              v-for="option in shadowOptions"
              :key="option.value"
              class="appearance-dialog__tick-label"
            >{{ option.label }}</span>
          </div>
        </section>

        <!-- 当前选中预览 -->
        <section class="appearance-dialog__current">
          <div
            class="appearance-dialog__current-preview"
            :style="{ boxShadow: currentOption.previewShadow }"
          />
          <div class="appearance-dialog__current-info">
            <span class="appearance-dialog__current-label">当前阴影</span>
            <span class="appearance-dialog__current-text">{{ currentOption.label }}</span>
            <span class="appearance-dialog__current-hint">{{ currentOption.hint }}</span>
          </div>
        </section>
      </VCardText>

      <VDivider />
      <VCardActions class="appearance-dialog__actions justify-center">
        <VBtn
          :slim="false"
          variant="tonal"
          color="primary"
          prepend-icon="mdi-check"
          @click="visible = false"
        >
          完成
        </VBtn>
      </VCardActions>
    </VCard>
  </VDialog>
</template>

<style scoped lang="scss">
/* 骨架样式统一管理在 styles/appearance-dialogs.css，此处只保留阴影预览的差异部分 */
.appearance-dialog__preview {
  border: 1.5px solid rgba(var(--v-theme-on-surface), 0.2);
  border-radius: var(--am-chip-radius, 8px);
  transition: box-shadow 0.2s ease;
}

.appearance-dialog__current-preview {
  border: 2px solid rgba(var(--v-theme-on-surface), 0.15);
  transition: box-shadow 0.2s ease;
}
</style>

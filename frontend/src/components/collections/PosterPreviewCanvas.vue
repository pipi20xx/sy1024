<script setup lang="ts">
/**
 * PosterPreviewCanvas — 海报预览画布
 *
 * CollectionPosterDialog / BatchPosterDialog 共用的预览画布：
 * 底图层 + 可拖拽的文字层，内部维护拖拽偏移与底图缩放系数。
 * 父组件在保存时通过模板 ref 读取 expose 的 visualOffset / scaleFactor
 * 换算成原图像素偏移量传给后端。
 */
import { ref, reactive, watch } from 'vue'
import type { PosterLayers } from '@/api/collectionPoster'

const props = defineProps<{
  /** 预览图层数据（null 时显示空态） */
  layers: PosterLayers | null
  /** 是否正在生成（显示加载圈） */
  isGenerating?: boolean
  /** 生成种子，变更后强制重建画布 */
  seed?: number
}>()

const imgRef = ref<HTMLImageElement | null>(null)
const scaleFactor = ref(1.0)

// ── 拖拽 ──
const visualOffset = reactive({ x: 0, y: 0 })
const isDragging = ref(false)
const dragStart = reactive({ x: 0, y: 0 })

// 图层被清空（对话框重新打开）时复位拖拽偏移
watch(() => props.layers, (layers) => {
  if (!layers) {
    visualOffset.x = 0
    visualOffset.y = 0
    scaleFactor.value = 1.0
  }
})

/** 底图加载后按渲染尺寸换算缩放系数（预览尺寸 → 原图像素） */
function updateScaleFactor() {
  if (imgRef.value) {
    const rect = imgRef.value.getBoundingClientRect()
    const naturalW = imgRef.value.naturalWidth || 1000
    if (rect.width > 0) scaleFactor.value = naturalW / rect.width
  }
}

function onMouseDown(e: MouseEvent) {
  if (!props.layers) return
  isDragging.value = true
  dragStart.x = e.clientX - visualOffset.x
  dragStart.y = e.clientY - visualOffset.y
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e: MouseEvent) {
  if (!isDragging.value) return
  e.preventDefault()
  visualOffset.x = e.clientX - dragStart.x
  visualOffset.y = e.clientY - dragStart.y
}

function onMouseUp() {
  isDragging.value = false
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
}

defineExpose({ visualOffset, scaleFactor })
</script>

<template>
  <div class="ppc-root">
    <v-progress-circular v-if="isGenerating" indeterminate color="primary" size="32" />
    <div v-else-if="layers" :key="seed" class="ppc-stage">
      <img
        ref="imgRef"
        :src="'data:image/jpeg;base64,' + layers.base"
        class="ppc-base poster-rounded"
        @load="updateScaleFactor"
      />
      <div
        class="ppc-text-layer"
        :style="{
          transform: `translate(${visualOffset.x}px, ${visualOffset.y}px)`,
          cursor: isDragging ? 'grabbing' : 'grab',
        }"
        @mousedown="onMouseDown"
      >
        <img
          :src="'data:image/png;base64,' + layers.text"
          draggable="false"
          class="ppc-text-img"
        />
      </div>
    </div>
    <div v-else class="text-center text-medium-emphasis">
      <slot name="empty">
        <v-icon size="48" color="grey-lighten-1" class="mb-2">mdi-palette-outline</v-icon>
        <p class="text-caption">点击"更新预览"生成</p>
      </slot>
    </div>
  </div>
</template>

<style scoped>
.ppc-root {
  width: 100%;
}

/* 画布舞台：固定 2:3 海报宽高比，文字层相对其定位 */
.ppc-stage {
  position: relative;
  width: 100%;
  aspect-ratio: 2 / 3;
}

.ppc-base {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.ppc-text-layer {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.ppc-text-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  pointer-events: none;
}
</style>

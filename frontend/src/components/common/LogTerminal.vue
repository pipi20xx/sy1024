<script setup lang="ts">
/**
 * LogTerminal — 全局日志终端组件
 *
 * 参考 MoviePilot 实时日志视图的交互：
 * - 级别按钮组筛选 + 关键字搜索 + 暂停/恢复实时流
 * - 同一秒同一级别的日志合并为一组（左侧时间列只显示一次 + 彩色级别侧条）
 * - 向上滚动时暂停跟随，右下角浮出"跳到最新 (N)"按钮
 *
 * 使用 systemStore.showLogModal 控制显隐，
 * 底层使用 GlassDialog 弹窗 + Vuetify 组件，数据来自 WebSocket 实时日志流
 */
import { ref, computed, nextTick, watch } from 'vue'
import { useSystemStore } from '@/stores'
import { GlassDialog } from '@/glass'

// --- 常量 ---
const MAX_DISPLAY_LINES = 1000   // 视图最多渲染的原始日志行数
const SCROLL_BOTTOM_THRESHOLD = 32 // 距底部多少像素内视为"贴着底部"

type LogEntry = {
  id: number
  time: string
  level: string
  message: string
}

type LogGroup = {
  key: string
  time: string
  level: string
  items: LogEntry[]
}

const systemStore = useSystemStore()
const viewportRef = ref<HTMLElement>()

// --- 筛选与流控制状态 ---
const selectedLevel = ref('ALL')
const searchQuery = ref('')
const isPaused = ref(false)
const followTail = ref(true)
const pendingLogCount = ref(0)
const frozenLogs = ref<string[]>([]) // 暂停时的显示快照

const levelOptions = [
  { title: '全部', value: 'ALL', color: 'primary' },
  { title: 'DEBUG', value: 'DEBUG', color: 'secondary' },
  { title: 'INFO', value: 'INFO', color: '#4ecdc4' },
  { title: 'WARNING', value: 'WARNING', color: '#FFB74D' },
  { title: 'ERROR', value: 'ERROR', color: '#EF5350' },
]

// --- 日志解析 ---
const ANSI_PATTERN = /\u001B\[[0-9;]*m/g
// 后端 WS 日志格式: "HH:MM:SS | LEVEL | message"（level 为 %-5s 补位）
const LINE_PATTERN = /^(\d{2}:\d{2}:\d{2})\s*\|\s*([A-Za-z]+)\s*\|\s*([\s\S]*)$/

let logSequence = 0

function stripAnsi(text: string): string {
  return text.replace(ANSI_PATTERN, '')
}

/** 规范化级别名：WARN→WARNING / FATAL→CRITICAL */
function normalizeLevel(level: string): string {
  const upper = level.trim().toUpperCase()
  if (upper === 'WARN') return 'WARNING'
  if (upper === 'FATAL') return 'CRITICAL'
  return upper
}

/** 无结构前缀的行按关键字猜测级别 */
function sniffLevel(text: string): string {
  const upper = text.toUpperCase()
  if (upper.includes('CRITICAL')) return 'CRITICAL'
  if (upper.includes('ERROR')) return 'ERROR'
  if (upper.includes('WARNING')) return 'WARNING'
  if (upper.includes('DEBUG')) return 'DEBUG'
  return 'INFO'
}

/**
 * 将原始日志行解析为展示条目。
 * 多行消息的续行（无 "时间 | 级别 |" 前缀）并入上一条，并继承其时间与级别。
 */
function parseEntries(raws: string[]): LogEntry[] {
  const entries: LogEntry[] = []
  for (const raw of raws) {
    for (const line of raw.split(/\r?\n/)) {
      const text = stripAnsi(line).trimEnd()
      if (!text.trim()) continue

      const m = text.match(LINE_PATTERN)
      if (m) {
        entries.push({ id: ++logSequence, time: m[1], level: normalizeLevel(m[2]), message: m[3] })
      } else if (entries.length) {
        // 续行：并入上一条记录
        const prev = entries[entries.length - 1]
        prev.message += '\n' + text
      } else {
        entries.push({ id: ++logSequence, time: '', level: sniffLevel(text), message: text })
      }
    }
  }
  return entries
}

// 暂停时冻结快照，恢复后重新同步最新数据
const displayedLogs = computed(() => {
  const src = isPaused.value ? frozenLogs.value : systemStore.logs
  return src.slice(-MAX_DISPLAY_LINES)
})

// --- 筛选 ---
const normalizedQuery = computed(() => searchQuery.value.trim().toLowerCase())

function matchesFilter(item: LogEntry): boolean {
  const levelOk =
    selectedLevel.value === 'ALL' ||
    item.level === selectedLevel.value ||
    (selectedLevel.value === 'ERROR' && item.level === 'CRITICAL')
  if (!levelOk) return false
  if (!normalizedQuery.value) return true
  return `${item.time} ${item.level} ${item.message}`.toLowerCase().includes(normalizedQuery.value)
}

// --- 分组：相邻且同秒同级别的条目合并 ---
const groupedLogs = computed<LogGroup[]>(() => {
  const groups: LogGroup[] = []
  for (const entry of parseEntries(displayedLogs.value)) {
    if (!matchesFilter(entry)) continue
    const last = groups[groups.length - 1]
    if (last && last.time === entry.time && last.level === entry.level) {
      last.items.push(entry)
    } else {
      groups.push({ key: `g${entry.id}`, time: entry.time, level: entry.level, items: [entry] })
    }
  }
  return groups
})

const visibleEntryCount = computed(() => groupedLogs.value.reduce((n, g) => n + g.items.length, 0))

// --- 滚动跟随 ---
function isNearBottom(): boolean {
  const el = viewportRef.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight <= SCROLL_BOTTOM_THRESHOLD
}

function scrollToBottom(behavior: ScrollBehavior = 'auto') {
  viewportRef.value?.scrollTo({ top: viewportRef.value.scrollHeight, behavior })
}

function enableFollow(behavior: ScrollBehavior = 'auto') {
  followTail.value = true
  pendingLogCount.value = 0
  nextTick(() => scrollToBottom(behavior))
}

function handleScroll() {
  if (isNearBottom()) {
    followTail.value = true
    pendingLogCount.value = 0
  } else {
    followTail.value = false
  }
}

// 新日志到达：跟随则滚底，否则累计待查看条数
watch(visibleEntryCount, (cur, prev) => {
  if (prev === undefined || cur <= prev) return
  if (followTail.value) {
    nextTick(() => scrollToBottom())
  } else {
    pendingLogCount.value += cur - prev
  }
})

// 打开弹窗时回到实时底部
watch(() => systemStore.showLogModal, (val) => {
  if (val) enableFollow()
})

// 切换筛选后回到实时底部
watch([selectedLevel, searchQuery], () => enableFollow())

// --- 暂停 / 恢复 ---
function togglePause() {
  if (!isPaused.value) {
    frozenLogs.value = [...systemStore.logs]
    isPaused.value = true
  } else {
    isPaused.value = false
    frozenLogs.value = []
    enableFollow()
  }
}

function clearLogs() {
  systemStore.clearLogs()
  frozenLogs.value = []
  pendingLogCount.value = 0
  followTail.value = true
}
</script>

<template>
  <GlassDialog v-model="systemStore.showLogModal" :max-width="1280" :cancel-visible="false">
    <template #title>
      <v-icon start>mdi-card-text-outline</v-icon>
      系统日志
      <span class="log-live-dot" :class="{ 'is-paused': isPaused }" :title="isPaused ? '已暂停' : '实时接收中'" />
    </template>

    <!-- 工具栏：级别筛选 / 搜索 / 暂停 / 清空 -->
    <div class="log-toolbar">
      <v-btn-toggle
        v-model="selectedLevel"
        mandatory
        divided
        density="compact"
        variant="tonal"
        class="log-level-toggle"
      >
        <v-btn
          v-for="opt in levelOptions"
          :key="opt.value"
          :value="opt.value"
          :color="opt.color"
        >
          {{ opt.title }}
        </v-btn>
      </v-btn-toggle>

      <v-text-field
        v-model="searchQuery"
        class="log-search"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        prepend-inner-icon="mdi-magnify"
        placeholder="搜索日志..."
      />

      <v-btn icon variant="text" :color="isPaused ? 'warning' : 'success'" @click="togglePause">
        <v-icon>{{ isPaused ? 'mdi-play' : 'mdi-pause' }}</v-icon>
        <v-tooltip activator="parent" location="bottom">{{ isPaused ? '恢复实时滚动' : '暂停实时滚动' }}</v-tooltip>
      </v-btn>

      <v-btn icon variant="text" color="error" @click="clearLogs">
        <v-icon>mdi-delete-outline</v-icon>
        <v-tooltip activator="parent" location="bottom">清空日志</v-tooltip>
      </v-btn>
    </div>

    <!-- 日志视口 -->
    <div ref="viewportRef" class="log-viewport" @scroll.passive="handleScroll">
      <div v-if="groupedLogs.length === 0" class="log-empty">
        <v-icon size="20">mdi-console-line</v-icon>
        <span>{{ visibleEntryCount === 0 && systemStore.logs.length === 0 ? '暂无日志' : '没有匹配的日志' }}</span>
      </div>

      <div v-else class="log-list">
        <div v-for="group in groupedLogs" :key="group.key" class="log-group">
          <div class="log-group__time">{{ group.time || '···' }}</div>
          <div class="log-group__panel">
            <div class="log-group__accent" :class="`level-${group.level.toLowerCase()}`" />
            <div class="log-group__lines">
              <div v-for="item in group.items" :key="item.id" class="log-line">
                <span class="log-line__level" :class="`level-${item.level.toLowerCase()}`">{{ item.level }}</span>
                <span class="log-line__msg">{{ item.message }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 未跟随底部时的"跳到最新"浮动按钮 -->
      <div v-if="pendingLogCount > 0 && !followTail" class="log-jump">
        <v-btn size="small" color="primary" variant="elevated" prepend-icon="mdi-arrow-down" @click="enableFollow('smooth')">
          跳到最新 ({{ pendingLogCount }})
        </v-btn>
      </div>
    </div>
  </GlassDialog>
</template>

<style scoped>
/* 标题栏实时状态小圆点 */
.log-live-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-left: 8px;
  border-radius: 50%;
  background-color: rgb(var(--v-theme-success));
  box-shadow: 0 0 6px rgb(var(--v-theme-success));
  animation: log-live-pulse 2s ease-in-out infinite;
}
.log-live-dot.is-paused {
  background-color: rgb(var(--v-theme-warning));
  box-shadow: none;
  animation: none;
}
@keyframes log-live-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

/* 工具栏 */
.log-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.log-level-toggle {
  flex: 0 0 auto;
  text-transform: none;
}
.log-level-toggle .v-btn {
  min-width: auto;
  padding: 0 10px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: none;
}
.log-search {
  flex: 1 1 160px;
  min-width: 120px;
}

/* 日志视口：仅负责布局与滚动，装饰交给全局玻璃主题；滚动条由 visual.css 统一管理 */
.log-viewport {
  position: relative;
  height: 70vh;
  min-height: 400px;
  overflow-y: auto;
  padding: 4px 2px;
}

/* 小屏（笔记本矮屏/移动端）适当收缩，避免弹窗超出可视区 */
@media (max-height: 820px) {
  .log-viewport {
    height: 62vh;
    min-height: 320px;
  }
}

.log-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 100%;
  min-height: 200px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

/* 分组：左侧时间列 + 右侧内容 */
.log-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.log-group {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  align-items: start;
  gap: 8px;
}
.log-group__time {
  padding-top: 6px;
  color: rgb(var(--v-theme-primary));
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  font-size: 0.78rem;
  font-weight: 600;
  white-space: nowrap;
}
.log-group__panel {
  display: flex;
  align-items: stretch;
  gap: 8px;
  padding: 2px 0 2px 8px;
  min-width: 0;
}

/* 级别侧条 —— 颜色由 tokens.css 的 --am-log-* 按主题提供 */
.log-group__accent {
  flex: 0 0 4px;
  align-self: stretch;
  border-radius: 999px;
  background-color: rgba(var(--v-theme-on-surface), 0.24);
}
.log-group__accent.level-debug { background-color: var(--am-log-debug); }
.log-group__accent.level-info { background-color: var(--am-log-info); }
.log-group__accent.level-warning { background-color: var(--am-log-warning); }
.log-group__accent.level-error { background-color: var(--am-log-error); }
.log-group__accent.level-critical { background-color: var(--am-log-critical); }

.log-group__lines {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* 单行日志 */
.log-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
  font-size: 0.8rem;
  line-height: 1.6;
  color: rgba(var(--v-theme-on-surface), 0.88);
  min-width: 0;
}
.log-line__level {
  flex: 0 0 56px;
  font-weight: 700;
}
.log-line__level.level-debug { color: var(--am-log-debug); }
.log-line__level.level-info { color: var(--am-log-info); }
.log-line__level.level-warning { color: var(--am-log-warning); }
.log-line__level.level-error { color: var(--am-log-error); }
.log-line__level.level-critical { color: var(--am-log-critical); }
.log-line__msg {
  flex: 1;
  min-width: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* 跳到最新浮动按钮 */
.log-jump {
  position: sticky;
  bottom: 12px;
  display: flex;
  justify-content: flex-end;
  pointer-events: none;
  margin-top: 8px;
}
.log-jump :deep(.v-btn) {
  pointer-events: auto;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
}
</style>

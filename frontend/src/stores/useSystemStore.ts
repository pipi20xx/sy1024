import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ProgressData } from '@/types'
import { useItemStore } from './useItemStore'

export const useSystemStore = defineStore('system', () => {
  const scanProgress = ref<ProgressData>({ status: 'idle', current: 0, total: 0, message: '' })
  const downloadProgress = ref<ProgressData>({ status: 'idle', current: 0, total: 0, message: '' })
  const actorUpdateProgress = ref<ProgressData>({ status: 'idle', current: 0, total: 0, message: '' })
  const isConnected = ref(false)
  const fileWatcherMessage = ref<string>('')
  const fileWatcherTimestamp = ref<number>(0)  // 用于触发列表自动刷新
  // 原始日志行（"HH:MM:SS | LEVEL | message"），由 LogTerminal 自行解析与筛选
  const logs = ref<string[]>([])
  const showLogModal = ref(false)
  const MAX_LOGS = 1000

  let socket: WebSocket | null = null
  let reconnectInterval: ReturnType<typeof setInterval> | null = null

  function connect() {
    if (socket) return
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    socket = new WebSocket(`${protocol}//${host}/ws`)

    socket.onopen = () => {
      isConnected.value = true
      if (reconnectInterval) { clearInterval(reconnectInterval); reconnectInterval = null }
    }

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data)
        if (payload.type === 'progress') {
          const task = payload.task
          if (task === 'scan') {
            scanProgress.value = payload.data
          } else if (task === 'download' || task === 'download_file' || task === 'import_collection' ||
                     task === 'import_actors' || task === 'update_actors_override' ||
                     task === 'batch_poster' || task === 'batch_workflow') {
            downloadProgress.value = payload.data
          } else if (task === 'actor_update') {
            actorUpdateProgress.value = payload.data
          }
        } else if (payload.type === 'file_watcher') {
          fileWatcherMessage.value = payload.data?.message || ''
          fileWatcherTimestamp.value = Date.now()
        } else if (payload.type === 'library_status') {
          // 异步入库状态更新：后端查询完毕后推送，更新对应 items 的 in_library 字段
          const itemStore = useItemStore()
          itemStore.updateLibraryStatus(payload.data?.item_type, payload.data?.statuses || {})
        } else if (payload.type === 'log') {
          logs.value.push(payload.data)
          if (logs.value.length > MAX_LOGS) {
            logs.value = logs.value.slice(-MAX_LOGS)
          }
        }
      } catch (e) { console.error('WS Parse Error', e) }
    }

    socket.onclose = () => {
      isConnected.value = false
      socket = null
      if (!reconnectInterval) reconnectInterval = setInterval(() => connect(), 5000)
    }

    socket.onerror = (err) => console.error('WebSocket Error', err)
  }

  function clearLogs() { logs.value = [] }

  function disconnect() {
    if (socket) {
      // 主动断开时不触发 onclose，避免重新启动重连定时器
      socket.onclose = null
      socket.close()
      socket = null
    }
    if (reconnectInterval) {
      clearInterval(reconnectInterval)
      reconnectInterval = null
    }
    isConnected.value = false
  }

  return {
    scanProgress, downloadProgress, actorUpdateProgress,
    isConnected, logs, showLogModal,
    fileWatcherMessage, fileWatcherTimestamp,
    connect, disconnect, clearLogs,
  }
})

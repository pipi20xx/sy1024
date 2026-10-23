/**
 * WebSocket 连接管理 composable
 * 自动重连、进度/日志消息分发
 */
import { ref, onUnmounted } from 'vue'
import type { ProgressData } from '@/types'

export function useWebSocket() {
  const isConnected = ref(false)
  const scanProgress = ref<ProgressData>({ status: 'idle', current: 0, total: 0, message: '' })
  const downloadProgress = ref<ProgressData>({ status: 'idle', current: 0, total: 0, message: '' })
  const actorUpdateProgress = ref<ProgressData>({ status: 'idle', current: 0, total: 0, message: '' })
  const logs = ref<string[]>([])
  const MAX_LOGS = 500

  let socket: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setInterval> | null = null

  function connect() {
    if (socket) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/ws`

    socket = new WebSocket(wsUrl)

    socket.onopen = () => {
      isConnected.value = true
      if (reconnectTimer) {
        clearInterval(reconnectTimer)
        reconnectTimer = null
      }
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
        } else if (payload.type === 'log') {
          logs.value.push(payload.data)
          if (logs.value.length > MAX_LOGS) {
            logs.value = logs.value.slice(-MAX_LOGS)
          }
        }
      } catch (e) {
        console.error('WS Message Parse Error', e)
      }
    }

    socket.onclose = () => {
      isConnected.value = false
      socket = null
      if (!reconnectTimer) {
        reconnectTimer = setInterval(() => {
          connect()
        }, 5000)
      }
    }

    socket.onerror = (err) => {
      console.error('WebSocket Error', err)
    }
  }

  function disconnect() {
    if (socket) {
      socket.close()
      socket = null
    }
    if (reconnectTimer) {
      clearInterval(reconnectTimer)
      reconnectTimer = null
    }
    isConnected.value = false
  }

  function clearLogs() {
    logs.value = []
  }

  onUnmounted(() => {
    disconnect()
  })

  return {
    isConnected,
    scanProgress,
    downloadProgress,
    actorUpdateProgress,
    logs,
    connect,
    disconnect,
    clearLogs,
  }
}

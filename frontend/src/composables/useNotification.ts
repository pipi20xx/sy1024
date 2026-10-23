/**
 * 通知封装 composable
 * 底层使用 Vuetify snackbar，在 App.vue 中挂载
 */
import { ref } from 'vue'

interface NotificationState {
  show: boolean
  message: string
  title?: string
  color: string
  timeout: number
}

const state = ref<NotificationState>({
  show: false,
  message: '',
  title: '',
  color: 'success',
  timeout: 3000,
})

export function useNotification() {
  /**
   * 显示通知
   * @param titleOrMsg 标题或消息
   * @param message 消息内容（可选）
   * @param type 类型 success/error/warning/info
   */
  function notify(titleOrMsg: string, message?: string, type: 'success' | 'error' | 'warning' | 'info' = 'success') {
    state.value = {
      show: true,
      title: message ? titleOrMsg : '',
      message: message || titleOrMsg,
      color: type === 'error' ? 'error' : type === 'warning' ? 'warning' : type === 'info' ? 'info' : 'success',
      timeout: type === 'error' ? 5000 : 3000,
    }
  }

  function success(msg: string) { notify(msg, undefined, 'success') }
  function error(msg: string) { notify(msg, undefined, 'error') }
  function warning(msg: string) { notify(msg, undefined, 'warning') }
  function info(msg: string) { notify(msg, undefined, 'info') }

  return { state, notify, success, error, warning, info }
}

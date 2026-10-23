/**
 * 确认对话框 composable（单例模式）
 * 用法：const { confirm } = useConfirm()
 *       await confirm({ title: '确认删除', content: '确定要删除吗？' })
 *
 * ConfirmDialog.vue 中使用同一个 composable 来渲染对话框 UI
 */
import { ref, watch } from 'vue'

interface ConfirmOptions {
  title: string
  content: string
  confirmText?: string
  cancelText?: string
  confirmColor?: string
}

// 模块级单例状态
const show = ref(false)
const options = ref<ConfirmOptions>({
  title: '',
  content: '',
  confirmText: '确认',
  cancelText: '取消',
  confirmColor: 'primary',
})

let resolvePromise: ((value: boolean) => void) | null = null
let confirmed = false

export function useConfirm() {
  function confirm(opts: ConfirmOptions): Promise<boolean> {
    options.value = {
      confirmText: '确认',
      cancelText: '取消',
      confirmColor: 'primary',
      ...opts,
    }
    confirmed = false
    show.value = true
    return new Promise((resolve) => {
      resolvePromise = resolve
    })
  }

  function onConfirm() {
    confirmed = true
    show.value = false
  }

  function onCancel() {
    // 直接关闭对话框，watch 会负责 resolve
    show.value = false
  }

  // 统一在 show 变为 false 时 resolve Promise
  // 这样无论是点击确认、取消、外部遮罩、ESC 还是 X 按钮，
  // 都能正确关闭并 resolve，且动画行为与普通 dialog 一致
  watch(show, (val) => {
    if (!val && resolvePromise) {
      resolvePromise(confirmed)
      resolvePromise = null
    }
  })

  return {
    show,
    options,
    confirm,
    onConfirm,
    onCancel,
  }
}

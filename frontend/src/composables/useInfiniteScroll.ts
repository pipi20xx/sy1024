/**
 * 无限滚动 composable
 * 替换手动 window.innerWidth 监听
 * 支持 keep-alive：通过 onActivated/onDeactivated 正确管理监听器
 */
import { onMounted, onUnmounted, onActivated, onDeactivated } from 'vue'

interface UseInfiniteScrollOptions {
  /**
   * 距底部多少像素时触发加载
   */
  distance?: number
  /**
   * 加载函数，返回 void
   */
  onLoad: () => void | Promise<void>
  /**
   * 是否还有更多数据
   */
  hasMore: () => boolean
  /**
   * 是否正在加载
   */
  isLoading: () => boolean
}

export function useInfiniteScroll(options: UseInfiniteScrollOptions) {
  const { distance = 300, onLoad, hasMore, isLoading } = options

  function handleScroll() {
    const scrollTop = document.documentElement.scrollTop || document.body.scrollTop
    const clientHeight = window.innerHeight
    const scrollHeight = document.documentElement.scrollHeight || document.body.scrollHeight

    const shouldLoad = scrollTop + clientHeight >= scrollHeight - distance
    if (shouldLoad && hasMore() && !isLoading()) {
      onLoad()
    }
  }

  function addListener() {
    window.addEventListener('scroll', handleScroll, { passive: true })
  }

  function removeListener() {
    window.removeEventListener('scroll', handleScroll)
  }

  // 首次挂载
  onMounted(addListener)
  onUnmounted(removeListener)

  // keep-alive 激活/停用
  onActivated(addListener)
  onDeactivated(removeListener)

  return { handleScroll }
}

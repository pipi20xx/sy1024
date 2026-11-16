/**
 * 轻量后台定时器 —— 移植自 MoviePilot-Frontend `backgroundManager` 的定时器思路：
 *
 * 前台活跃时按间隔回调，切到后台自动暂停、回前台恢复；
 * 系统开启「减少动态效果」时回调不再触发。
 */

export interface BackgroundTimerHandle {
  stop: () => void
  pause: () => void
  resume: () => void
}

export interface BackgroundTimerOptions {
  /** 轮换间隔（秒）。 */
  intervalSeconds: number
  /** 定时回调。 */
  onTick: () => void
  /** 返回 true 表示当前应暂停回调（例如系统减少动态效果）。 */
  reducedMotion: () => boolean
  /** 启动时是否立即执行一次回调。 */
  runImmediately?: boolean
}

export function createBackgroundTimer(options: BackgroundTimerOptions): BackgroundTimerHandle {
  const { intervalSeconds, onTick, reducedMotion, runImmediately = false } = options

  let timer: ReturnType<typeof setInterval> | null = null
  let running = true

  const canRun = () => !reducedMotion() && document.visibilityState !== 'hidden'

  const clear = () => {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  const schedule = () => {
    clear()
    timer = setInterval(() => {
      if (canRun()) onTick()
    }, Math.max(intervalSeconds, 1) * 1000)
  }

  const start = () => {
    running = true
    if (runImmediately) onTick()
    schedule()
  }

  const stop = () => {
    running = false
    clear()
  }

  const pause = () => clear()

  const resume = () => {
    if (!running) return
    schedule()
  }

  const onVisibility = () => {
    if (document.visibilityState === 'hidden') pause()
    else resume()
  }

  document.addEventListener('visibilitychange', onVisibility)
  start()

  return {
    stop: () => {
      document.removeEventListener('visibilitychange', onVisibility)
      stop()
    },
    pause,
    resume,
  }
}

/**
 * localStorage / sessionStorage composable
 */
import { ref, watch, type Ref } from 'vue'

export function useLocalStorage<T>(key: string, defaultValue: T): Ref<T> {
  const storedValue = localStorage.getItem(key)
  const data = ref<T>(storedValue ? JSON.parse(storedValue) : defaultValue) as Ref<T>

  watch(
    data,
    (newValue) => {
      localStorage.setItem(key, JSON.stringify(newValue))
    },
    { deep: true }
  )

  return data
}

export function useSessionStorage<T>(key: string, defaultValue: T): Ref<T> {
  const storedValue = sessionStorage.getItem(key)
  const data = ref<T>(storedValue ? JSON.parse(storedValue) : defaultValue) as Ref<T>

  watch(
    data,
    (newValue) => {
      sessionStorage.setItem(key, JSON.stringify(newValue))
    },
    { deep: true }
  )

  return data
}

export function removeLocalStorage(key: string): void {
  localStorage.removeItem(key)
}

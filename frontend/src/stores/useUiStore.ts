import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

/**
 * 可选的每行卡片数量。
 * Vuetify 栅格系统为 12 列，只能整除为 1/2/3/4/6/12。
 * 0 表示"默认（自适应）"，使用响应式断点。
 */
export const CARDS_PER_ROW_OPTIONS = [
  { title: '默认（自适应）', value: 0 },
  { title: '2', value: 2 },
  { title: '3', value: 3 },
  { title: '4', value: 4 },
  { title: '6', value: 6 },
  { title: '12', value: 12 },
] as const

export const useUiStore = defineStore('ui', () => {
  /** 每行卡片数量，0=自适应 */
  const cardsPerRow = ref<number>(Number(localStorage.getItem('ui_cards_per_row')) || 0)

  function setCardsPerRow(val: number) {
    cardsPerRow.value = val
    localStorage.setItem('ui_cards_per_row', String(val))
  }

  /** 供 v-col 使用的计算属性：null=自适应响应式，数字=固定 cols */
  const gridColProps = computed(() => {
    if (cardsPerRow.value === 0) {
      return { cols: '6', sm: '4', md: '3', lg: '2', xl: '2' }
    }
    return { cols: String(Math.floor(12 / cardsPerRow.value)) }
  })

  return { cardsPerRow, setCardsPerRow, gridColProps }
})

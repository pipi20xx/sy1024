// frontend/src/constants/tagManagement.ts

export interface Country {
  iso_3166_1: string
  native_name: string
}

export interface Genre {
  id: number
  name: string
}

export const countries: Country[] = [
  { iso_3166_1: 'US', native_name: '美国' },
  { iso_3166_1: 'GB', native_name: '英国' },
  { iso_3166_1: 'FR', native_name: '法国' },
  { iso_3166_1: 'DE', native_name: '德国' },
  { iso_3166_1: 'IT', native_name: '意大利' },
  { iso_3166_1: 'ES', native_name: '西班牙' },
  { iso_3166_1: 'CA', native_name: '加拿大' },
  { iso_3166_1: 'AU', native_name: '澳大利亚' },
  { iso_3166_1: 'JP', native_name: '日本' },
  { iso_3166_1: 'KR', native_name: '韩国' },
  { iso_3166_1: 'CN', native_name: '中国大陆' },
  { iso_3166_1: 'HK', native_name: '中国香港' },
  { iso_3166_1: 'TW', native_name: '中国台湾' },
  { iso_3166_1: 'MO', native_name: '中国澳门' },
  { iso_3166_1: 'RU', native_name: '俄罗斯' },
  { iso_3166_1: 'IN', native_name: '印度' },
  { iso_3166_1: 'BR', native_name: '巴西' },
  { iso_3166_1: 'MX', native_name: '墨西哥' },
  { iso_3166_1: 'SE', native_name: '瑞典' },
  { iso_3166_1: 'DK', native_name: '丹麦' },
  { iso_3166_1: 'NO', native_name: '挪威' },
  { iso_3166_1: 'NL', native_name: '荷兰' },
  { iso_3166_1: 'BE', native_name: '比利时' },
  { iso_3166_1: 'IE', native_name: '爱尔兰' },
  { iso_3166_1: 'PL', native_name: '波兰' },
  { iso_3166_1: 'TH', native_name: '泰国' },
  { iso_3166_1: 'SA', native_name: '沙特阿拉伯' },
]

export const genres: Genre[] = [
  { id: 28, name: '动作' },
  { id: 12, name: '冒险' },
  { id: 16, name: '动画' },
  { id: 35, name: '喜剧' },
  { id: 80, name: '犯罪' },
  { id: 99, name: '纪录片' },
  { id: 18, name: '剧情' },
  { id: 10751, name: '家庭' },
  { id: 14, name: '奇幻' },
  { id: 36, name: '历史' },
  { id: 27, name: '恐怖' },
  { id: 10402, name: '音乐' },
  { id: 9648, name: '悬疑' },
  { id: 10749, name: '爱情' },
  { id: 878, name: '科幻' },
  { id: 10770, name: '电视电影' },
  { id: 53, name: '惊悚' },
  { id: 10752, name: '战争' },
  { id: 37, name: '西部' },
  { id: 10759, name: '动作冒险' },
  { id: 10762, name: '儿童' },
  { id: 10763, name: '新闻' },
  { id: 10764, name: '真人秀' },
  { id: 10765, name: '科幻奇幻' },
  { id: 10766, name: '肥皂剧' },
  { id: 10767, name: '脱口秀' },
  { id: 10768, name: '战争政治' },
]

export function getCountryName(code: string): string {
  return countries.find(c => c.iso_3166_1 === code)?.native_name || code
}

export function getGenreName(id: number): string {
  return genres.find(g => g.id === id)?.name || String(id)
}

import { api } from './client'
import type { TagRule } from '@/types'

const BASE_PATH = '/api/tags/rules'

export const fetchTagRules = () => api.get<TagRule[]>(BASE_PATH)

export const addTagRule = (ruleData: Omit<TagRule, 'id'>) => api.post<TagRule>(BASE_PATH, ruleData)

export const updateTagRule = (ruleId: string, ruleData: TagRule) => api.put<TagRule>(`${BASE_PATH}/${ruleId}`, ruleData)

export const deleteTagRule = (ruleId: string) => api.delete<void>(`${BASE_PATH}/${ruleId}`)

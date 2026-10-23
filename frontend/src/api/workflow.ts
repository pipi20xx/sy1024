import { api } from './client'
import type { ItemType } from '@/types'

export interface WorkflowTask {
  type: string
  params?: Record<string, any>
  description?: string
}

export interface WorkflowRequest {
  item_type: ItemType
  tasks: WorkflowTask[]
  interval_seconds: number
  item_ids?: string[]
  filters?: Record<string, any>
}

export async function runWorkflow(data: WorkflowRequest): Promise<{ message: string }> {
  return api.post('/api/workflow/run', data)
}

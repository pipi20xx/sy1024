import { api as client } from './client';

export interface ScheduledTask {
  id: number;
  name: string;
  task_type: string;
  cron_expression: string;
  enabled: boolean;
  last_run: string | null;
  next_run: string | null;
  params: string;
}

export const tasksApi = {
  getTasks: () => client.get<ScheduledTask[]>('/api/tasks'),
  createTask: (data: Partial<ScheduledTask>) => client.post<ScheduledTask>('/api/tasks', data),
  updateTask: (id: number, data: Partial<ScheduledTask>) => client.patch<ScheduledTask>(`/api/tasks/${id}`, data),
  deleteTask: (id: number) => client.delete(`/api/tasks/${id}`),
  runTask: (id: number) => client.post(`/api/tasks/${id}/run`, {}),
};

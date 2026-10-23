
import { api } from './client';

export interface ExternalConfig {
  api_token: string | null;
  audit_log_enabled: boolean;
}

export interface AuditLog {
  id: number;
  timestamp: string;
  method: string;
  path: string;
  status_code: number;
  ip: string;
  query_params: string;
  payload: string;
  user_agent: string;
}

export interface AuditLogResponse {
  total: number;
  items: AuditLog[];
  page: number;
  size: number;
}

export const externalControlApi = {
  getConfig: () => api.get<ExternalConfig>('/api/external-control/config'),
  
  updateConfig: (config: Partial<ExternalConfig>) => 
    api.post<any>('/api/external-control/config', config),
    
  generateToken: () => 
    api.post<{token: string}>('/api/external-control/generate-token', {}),
    
  getAuditLogs: (params: {page: number, size: number, search?: string}) => 
    api.get<AuditLogResponse>('/api/external-control/audit-logs', { params }),
    
  getDocsUrl: () => {
    const token = localStorage.getItem('access_token');
    const base = '/api/external-control/docs-ui';
    return token ? `${base}?auth_token=${encodeURIComponent(token)}` : base;
  }
};

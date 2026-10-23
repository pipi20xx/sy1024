// frontend_new/src/api/client.ts

interface ApiOptions extends RequestInit {
  baseUrl?: string;
  params?: Record<string, string | number | boolean | undefined | null | (string | number | boolean)[]>;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''; // 默认从 Vite 环境变量获取，或为空

export async function apiFetch<T>(
  endpoint: string,
  options?: ApiOptions
): Promise<T> {
  const { baseUrl = API_BASE_URL, params, headers, body, method = 'GET', ...rest } = options || {};

  let url = `${baseUrl}${endpoint}`;

  if (params) {
    const queryString = new URLSearchParams();
    for (const key in params) {
      const value = params[key];
      if (value !== undefined && value !== null) {
        if (Array.isArray(value)) {
          value.forEach((v) => queryString.append(key, String(v)));
        } else {
          queryString.append(key, String(value));
        }
      }
    }
    if (queryString.toString()) {
      url += (url.includes('?') ? '&' : '?') + queryString.toString();
    }
  }

  const defaultHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  // 自动添加 Authorization 头
  const token = localStorage.getItem('access_token');
  if (token) {
    defaultHeaders['Authorization'] = `Bearer ${token}`;
  }

  // If body is FormData, let the browser set Content-Type (it needs boundary)
  if (body instanceof FormData) {
      delete defaultHeaders['Content-Type'];
  }

  const config: RequestInit = {
    method,
    headers: {
      ...defaultHeaders,
      ...headers,
    },
    ...rest,
  };

  if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
    if (body instanceof FormData) {
        config.body = body;
    } else {
        config.body = JSON.stringify(body);
    }
  }

  try {
    const response = await fetch(url, config);

    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
        
        if (!window.location.pathname.includes('/login')) {
             window.location.href = '/login';
        }
      }

      let errorData: any = { message: `HTTP error! status: ${response.status}` };
      try {
        errorData = await response.json();
      } catch (e) {
        // 如果不是 JSON 格式，就使用默认错误信息
      }
      throw new Error(errorData.detail || errorData.message || `API Error: ${response.status}`);
    }

    // 尝试解析 JSON，如果响应是 204 No Content 等，json() 会失败
    const text = await response.text();
    return text ? JSON.parse(text) : {} as T;

  } catch (error) {
    console.error('API Fetch Error:', error);
    throw error;
  }
}

// 封装常用的 HTTP 方法
export const api = {
  get: <T>(endpoint: string, options?: ApiOptions) => apiFetch<T>(endpoint, { ...options, method: 'GET' }),
  post: <T>(endpoint: string, body: any, options?: ApiOptions) => apiFetch<T>(endpoint, { ...options, method: 'POST', body }),
  put: <T>(endpoint: string, body: any, options?: ApiOptions) => apiFetch<T>(endpoint, { ...options, method: 'PUT', body }),
  patch: <T>(endpoint: string, body: any, options?: ApiOptions) => apiFetch<T>(endpoint, { ...options, method: 'PATCH', body }),
  delete: <T>(endpoint: string, options?: ApiOptions) => apiFetch<T>(endpoint, { ...options, method: 'DELETE' }),
};

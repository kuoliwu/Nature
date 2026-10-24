/** 與本地 FastAPI 後端溝通。型別對應 backend/app/schemas.py */

export type HealthOut = {
  status: string;
  app: string;
  db_initialized: boolean;
  needs_setup: boolean;
  server_time: string;
};

export type InitDBOut = {
  message: string;
  was_initialized: boolean;
  tables: string[];
  seeded: Record<string, number> | null;
};

export type DBStatusOut = {
  db_initialized: boolean;
  database: string;
  tables: { table: string; rows: number }[];
};

export type User = {
  id: number;
  name: string;
  phone: string;
  role: 'super_admin' | 'staff';
  is_active: boolean;
  permissions: string[];
  created_at: string;
};

export type LoginOut = { access_token: string; expires_at: string; user: User };
export type Permission = { code: string; label: string };

export type UserInput = {
  name?: string;
  phone?: string;
  password?: string;
  role?: User['role'];
  is_active?: boolean;
  permissions?: string[];
};

export type Project = {
  id: number;
  name: string;
  phone: string | null;
  community_address: string | null;
  community_manager: string | null;
  note: string | null;
  created_at: string;
};

export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

const TIMEOUT_MS = 8000;

// 由 AuthProvider 設定；畫面直接呼叫 api.xxx() 即可
const state: { baseUrl: string; token: string | null; onUnauthorized?: () => void } = {
  baseUrl: '',
  token: null,
};

export function configureApi(next: Partial<typeof state>) {
  Object.assign(state, next);
}

type RequestInit = {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  adminKey?: string; // 系統層級操作（建立資料庫 / 第一位管理者）
  baseUrl?: string; // 連線設定畫面測試尚未儲存的位址時使用
  auth?: boolean; // 帶上登入憑證，預設 true
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const baseUrl = init.baseUrl ?? state.baseUrl;
  if (!baseUrl) throw new ApiError('尚未設定主機位址');

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (init.body !== undefined) headers['Content-Type'] = 'application/json';
  if (init.adminKey) headers['X-Admin-Key'] = init.adminKey;
  if (init.auth !== false && state.token) headers.Authorization = `Bearer ${state.token}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${baseUrl}${path}`, {
      method: init.method ?? 'GET',
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: controller.signal,
    });
  } catch (e) {
    if (controller.signal.aborted) {
      throw new ApiError(`連線逾時（${TIMEOUT_MS / 1000} 秒）：請確認後端已啟動、位址正確、防火牆已開放`);
    }
    throw new ApiError(`無法連線到主機：${e instanceof Error ? e.message : String(e)}`);
  } finally {
    clearTimeout(timer);
  }

  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && init.auth !== false && state.token) state.onUnauthorized?.();
    const detail = data?.detail;
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg).join('\n')
          : `伺服器回應錯誤 (${res.status})`;
    throw new ApiError(res.status === 403 && init.adminKey ? '管理金鑰錯誤 (403)' : msg, res.status);
  }
  return data as T;
}

export const api = {
  // 系統
  health: (baseUrl?: string) => request<HealthOut>('/health', { baseUrl, auth: false }),
  initDb: (adminKey: string, baseUrl?: string) =>
    request<InitDBOut>('/init-db', { method: 'POST', body: {}, adminKey, baseUrl, auth: false }),
  dbStatus: (adminKey: string, baseUrl?: string) =>
    request<DBStatusOut>('/db/status', { adminKey, baseUrl, auth: false }),

  // 登入
  setup: (adminKey: string, body: { name: string; phone: string; password: string }) =>
    request<LoginOut>('/auth/setup', { method: 'POST', body, adminKey, auth: false }),
  login: (phone: string, password: string) =>
    request<LoginOut>('/auth/login', { method: 'POST', body: { phone, password }, auth: false }),
  me: () => request<User>('/auth/me'),
  changePassword: (old_password: string, new_password: string) =>
    request<LoginOut>('/auth/change-password', { method: 'POST', body: { old_password, new_password } }),

  // 人員
  permissions: () => request<Permission[]>('/permissions'),
  users: () => request<User[]>('/users'),
  createUser: (body: UserInput) => request<User>('/users', { method: 'POST', body }),
  updateUser: (id: number, body: UserInput) => request<User>(`/users/${id}`, { method: 'PATCH', body }),

  // 建案
  projects: () => request<Project[]>('/projects'),
};

/** 與本地 FastAPI 後端溝通。型別對應 backend/app/schemas.py */

export type HealthOut = {
  status: string;
  app: string;
  db_initialized: boolean;
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

export type ApiConfig = { baseUrl: string; adminKey: string };

export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

const TIMEOUT_MS = 8000;

async function request<T>(
  cfg: ApiConfig,
  path: string,
  init: { method?: 'GET' | 'POST'; body?: unknown; auth?: boolean } = {},
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (init.body !== undefined) headers['Content-Type'] = 'application/json';
  if (init.auth && cfg.adminKey) headers['X-Admin-Key'] = cfg.adminKey;

  let res: Response;
  try {
    res = await fetch(`${cfg.baseUrl}${path}`, {
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
    if (res.status === 403) throw new ApiError('管理金鑰錯誤 (403)', 403);
    if (res.status === 422 && init.auth && !cfg.adminKey) throw new ApiError('請輸入管理金鑰', 422);
    const detail = data?.detail;
    const msg = typeof detail === 'string' ? detail : `伺服器回應錯誤 (${res.status})`;
    throw new ApiError(msg, res.status);
  }
  return data as T;
}

export const api = {
  health: (cfg: ApiConfig) => request<HealthOut>(cfg, '/health'),

  initDb: (cfg: ApiConfig) =>
    request<InitDBOut>(cfg, '/init-db', { method: 'POST', body: {}, auth: true }),

  dbStatus: (cfg: ApiConfig) => request<DBStatusOut>(cfg, '/db/status', { auth: true }),
};

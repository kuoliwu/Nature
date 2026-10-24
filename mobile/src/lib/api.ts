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

export type ProjectInput = {
  name: string;
  phone?: string | null;
  address?: string | null; // 建案地址
  community_address?: string | null; // 社區地址
  community_manager?: string | null;
  note?: string | null;
};

export type Project = Required<ProjectInput> & {
  id: number;
  created_at: string;
  unit_count: number;
  batch_count: number;
};

export type UnitImportResult = {
  dry_run: boolean; // true：只檢查、沒有寫入
  created: string[];
  updated: string[];
  unchanged: number;
  errors: { row: number; message: string }[];
};

export type UnitInput = {
  unit_no: string;
  building?: string | null;
  floor?: string | null;
  address?: string | null;
  owner_name?: string | null;
  owner_phone?: string | null;
  owner_email?: string | null;
  area_ping?: number | null;
  handover_date?: string | null; // YYYY-MM-DD
  note?: string | null;
};

export type Unit = Required<UnitInput> & {
  id: number;
  project_id: number;
  report_upload_enabled: boolean;
};

export type BatchInput = {
  name: string;
  service_type: 'health_check' | 'inspection';
  start_date: string;
  end_date: string;
  day_start: string; // HH:MM
  day_end: string;
  slot_capacity: number;
  breaks: { start: string; end: string }[]; // 每天的屏蔽區段
};

export type Slot = {
  id: number;
  start_time: string; // HH:MM:SS
  end_time: string;
  capacity: number;
  booked: number;
  is_open: boolean;
  units: string[]; // 已預約的戶別
};

export type Batch = {
  id: number;
  project_id: number;
  name: string;
  service_type: 'health_check' | 'inspection';
  slot_minutes: number;
  slot_capacity: number;
  is_active: boolean;
  first_date: string | null;
  last_date: string | null;
  day_count: number;
  slot_count: number;
  open_slot_count: number;
  booked_count: number;
  description: string | null;
  booking_open_at: string | null;
  booking_close_at: string | null;
};

export type BatchDay = { date: string; slots: Slot[] };
export type BatchDetail = Batch & { days: BatchDay[] };

export type InviteStatus = {
  unit_id: number;
  unit_no: string;
  owner_name: string | null;
  owner_email: string | null;
  link: string | null;
  sent_at: string | null;
  send_count: number;
  last_opened_at: string | null;
  booking: {
    id: number;
    slot_id: number;
    date: string;
    start_time: string;
    end_time: string;
    contact_name: string;
    contact_phone: string;
    contact_email: string | null;
  } | null;
};

export type InviteSendResult = { sent: string[]; no_email: string[]; already_sent: string[]; already_booked: string[] };

export type BatchSettings = {
  description?: string | null;
  booking_open_at?: string | null; // YYYY-MM-DDTHH:MM:SS（本地時間）
  booking_close_at?: string | null;
};

export type CheckPoint = { id: number; name: string; is_active: boolean; sort_order: number };
export type ChecklistItem = CheckPoint & { check_points: CheckPoint[] };
export type ChecklistCategory = CheckPoint & { items: ChecklistItem[] };
export type ChecklistPatch = { name?: string; is_active?: boolean };

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

/** 給下載 / 上傳檔案（lib/files.ts）用 */
export function apiState(): { baseUrl: string; token: string | null } {
  return { baseUrl: state.baseUrl, token: state.token };
}

export function errorFromResponse(status: number, data: unknown): ApiError {
  const detail = (data as { detail?: unknown } | null)?.detail;
  const msg =
    typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map((d: { msg?: string }) => d.msg).join('\n')
        : `伺服器回應錯誤 (${status})`;
  if (status === 401 && state.token) state.onUnauthorized?.();
  return new ApiError(msg, status);
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
  project: (id: number) => request<Project>(`/projects/${id}`),
  createProject: (body: ProjectInput) => request<Project>('/projects', { method: 'POST', body }),
  updateProject: (id: number, body: Partial<ProjectInput>) =>
    request<Project>(`/projects/${id}`, { method: 'PATCH', body }),
  deleteProject: (id: number) => request<null>(`/projects/${id}`, { method: 'DELETE' }),

  // 住戶
  units: (projectId: number) => request<Unit[]>(`/projects/${projectId}/units`),
  unit: (id: number) => request<Unit>(`/units/${id}`),
  createUnit: (projectId: number, body: UnitInput) =>
    request<Unit>(`/projects/${projectId}/units`, { method: 'POST', body }),
  bulkCreateUnits: (projectId: number, unit_nos: string[]) =>
    request<{ created: string[]; skipped: string[] }>(`/projects/${projectId}/units/bulk`, {
      method: 'POST',
      body: { unit_nos },
    }),
  bulkCreateUnitsDetailed: (projectId: number, units: { unit_no: string; building: string; floor: string }[]) =>
    request<{ created: string[]; skipped: string[] }>(`/projects/${projectId}/units/bulk`, {
      method: 'POST',
      body: { units },
    }),
  unitsExportLink: (projectId: number, format: 'xlsx' | 'csv') =>
    request<{ url: string; filename: string; expires_at: string }>(
      `/projects/${projectId}/units/export-link?format=${format}`,
      { method: 'POST' },
    ),
  updateUnit: (id: number, body: Partial<UnitInput>) => request<Unit>(`/units/${id}`, { method: 'PATCH', body }),
  deleteUnit: (id: number) => request<null>(`/units/${id}`, { method: 'DELETE' }),

  // 健檢日期與時段
  batches: (projectId: number) => request<Batch[]>(`/projects/${projectId}/batches`),
  batch: (id: number) => request<BatchDetail>(`/batches/${id}`),
  createBatch: (projectId: number, body: BatchInput) =>
    request<BatchDetail>(`/projects/${projectId}/batches`, { method: 'POST', body }),
  addBatchDates: (id: number, body: Omit<BatchInput, 'name' | 'service_type' | 'slot_capacity'>) =>
    request<BatchDetail>(`/batches/${id}/dates`, { method: 'POST', body }),
  updateBatch: (id: number, body: { name?: string; is_active?: boolean }) =>
    request<Batch>(`/batches/${id}`, { method: 'PATCH', body }),
  deleteBatch: (id: number) => request<null>(`/batches/${id}`, { method: 'DELETE' }),
  updateSlot: (id: number, body: { is_open?: boolean; capacity?: number }) =>
    request<Slot>(`/slots/${id}`, { method: 'PATCH', body }),
  updateDay: (batchId: number, date: string, is_open: boolean) =>
    request<BatchDay>(`/batches/${batchId}/days/${date}`, { method: 'PATCH', body: { is_open } }),

  // 第二階段：預約邀請
  updateBatchSettings: (id: number, body: BatchSettings) =>
    request<Batch>(`/batches/${id}/settings`, { method: 'PATCH', body }),
  invites: (batchId: number) => request<InviteStatus[]>(`/batches/${batchId}/invites`),
  sendInvites: (batchId: number, body: { unit_ids?: number[]; resend?: boolean }) =>
    request<InviteSendResult>(`/batches/${batchId}/invites/send`, { method: 'POST', body }),
  inviteLink: (batchId: number, unitId: number) =>
    request<InviteStatus>(`/batches/${batchId}/units/${unitId}/invite-link`, { method: 'POST' }),
  cancelBooking: (bookingId: number) => request<null>(`/bookings/${bookingId}/cancel`, { method: 'POST' }),

  // 檢查項目清單（每個建案一份）
  checklist: (projectId: number) => request<ChecklistCategory[]>(`/projects/${projectId}/checklist`),
  addCategory: (projectId: number, name: string) =>
    request<ChecklistCategory>(`/projects/${projectId}/checklist/categories`, { method: 'POST', body: { name } }),
  updateCategory: (id: number, body: ChecklistPatch) =>
    request<ChecklistCategory>(`/checklist/categories/${id}`, { method: 'PATCH', body }),
  deleteCategory: (id: number) => request<null>(`/checklist/categories/${id}`, { method: 'DELETE' }),
  addItem: (categoryId: number, name: string) =>
    request<ChecklistCategory>(`/checklist/categories/${categoryId}/items`, { method: 'POST', body: { name } }),
  updateItem: (id: number, body: ChecklistPatch) =>
    request<ChecklistCategory>(`/checklist/items/${id}`, { method: 'PATCH', body }),
  deleteItem: (id: number) => request<ChecklistCategory>(`/checklist/items/${id}`, { method: 'DELETE' }),
  addPoint: (itemId: number, name: string) =>
    request<ChecklistCategory>(`/checklist/items/${itemId}/points`, { method: 'POST', body: { name } }),
  updatePoint: (id: number, body: ChecklistPatch) =>
    request<ChecklistCategory>(`/checklist/points/${id}`, { method: 'PATCH', body }),
  deletePoint: (id: number) => request<ChecklistCategory>(`/checklist/points/${id}`, { method: 'DELETE' }),
};

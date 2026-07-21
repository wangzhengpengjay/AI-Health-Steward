import type {
  ApiResponse,
  FamilyMember,
  FamilyMemberInput,
  MetricRecord,
  MetricRecordInput,
} from '@/types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// Generic fetch wrapper with JSON handling and error normalization
async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${BASE_URL}${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })

  if (!res.ok) {
    let message = `HTTP ${res.status}`
    try {
      const body = await res.json()
      message = body.detail ?? body.message ?? message
    } catch {
      // response body not JSON, use default message
    }
    throw new ApiError(message, res.status)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

// ---- Family Members ----

export const membersApi = {
  list: () => request<FamilyMember[]>('/members'),

  get: (id: string) => request<FamilyMember>(`/members/${id}`),

  create: (data: FamilyMemberInput) =>
    request<FamilyMember>('/members', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: Partial<FamilyMemberInput>) =>
    request<FamilyMember>(`/members/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<void>(`/members/${id}`, { method: 'DELETE' }),
}

// ---- Metric Records ----

export const metricsApi = {
  list: (memberId: string) =>
    request<MetricRecord[]>(`/members/${memberId}/metrics`),

  create: (memberId: string, data: MetricRecordInput) =>
    request<MetricRecord>(`/members/${memberId}/metrics`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    request<void>(`/metrics/${id}`, { method: 'DELETE' }),
}

// ---- Exported types for convenience ----
export type { ApiResponse, FamilyMember, MetricRecord }

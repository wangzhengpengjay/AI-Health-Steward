import type { ChatResponse,
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

  getByName: (memberId: string, metricName: string) =>
    request<MetricRecord[]>(`/members/${memberId}/metrics/${metricName}`),

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

// ===== Chat API =====

export const chatApi = {
  send: async (memberId: number, message: string, file?: File): Promise<ChatResponse> => {
    const formData = new FormData()
    formData.append('message', message)
    if (file) formData.append('file', file)
    const res = await fetch(`${BASE_URL}/members/${memberId}/chat`, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new ApiError(body.detail ?? `HTTP ${res.status}`, res.status)
    }
    return res.json()
  },

  stream: async function* (
    memberId: number,
    message: string,
    file?: File,
  ): AsyncGenerator<string> {
    const formData = new FormData()
    formData.append('message', message)
    if (file) formData.append('file', file)
    const res = await fetch(`${BASE_URL}/members/${memberId}/chat/stream`, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) throw new ApiError(`HTTP ${res.status}`, res.status)

    const reader = res.body?.getReader()
    if (!reader) throw new Error('No response body')

    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const raw = line.slice(6)
          if (raw === '[DONE]') return
          try {
            const parsed = JSON.parse(raw)
            if (parsed.delta) {
              yield parsed.delta
            } else if (parsed.error) {
              throw new Error(parsed.error)
            }
          } catch {
            // Not JSON, skip
          }
        }
      }
    }
  },
}

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

  get: (id: number) => request<FamilyMember>(`/members/${id}`),

  create: (data: FamilyMemberInput) =>
    request<FamilyMember>('/members', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: number, data: Partial<FamilyMemberInput>) =>
    request<FamilyMember>(`/members/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    request<void>(`/members/${id}`, { method: 'DELETE' }),
}

// ---- Metric Records ----

export const metricsApi = {
  list: (memberId: number) =>
    request<MetricRecord[]>(`/members/${memberId}/metrics`),

  getByName: (memberId: string, metricName: string) =>
    request<MetricRecord[]>(`/members/${memberId}/metrics/${metricName}`),

  create: (memberId: string, data: MetricRecordInput) =>
    request<MetricRecord>(`/members/${memberId}/metrics`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    request<void>(`/members/metrics/${id}`, { method: 'DELETE' }),

  update: (id: number, data: Partial<MetricRecordInput>) =>
    request<MetricRecord>(`/members/metrics/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
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
  ): AsyncGenerator<{ type: 'delta' | 'report' | 'error'; data: string }> {
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
              yield { type: 'delta', data: parsed.delta }
            } else if (parsed.report) {
              yield { type: 'report', data: parsed.report }
            } else if (parsed.error) {
              yield { type: 'error', data: parsed.error }
            }
         } catch {
           // Not JSON, skip
         }
       }
     }
    }
 },
}

// ---- Health Profile (diagnoses, medications, allergies) ----

export interface DiagnosisItem {
  id: number
  disease_name: string
  icd_code?: string
  diagnosed_date?: string
  severity?: string
  status: string
}

export interface MedicationItem {
  id: number
  drug_name: string
  generic_name?: string
  dosage: string
  frequency: string
  route: string
  start_date?: string
  end_date?: string
}

export interface AllergyItem {
  id: number
  type: string
  name: string
  severity: string
  recorded_at?: string
}

export interface LifestyleItem {
  id: number
  category: string
  status: string
  frequency?: string
  recorded_at?: string
}

export interface SurgeryItem {
  id: number
  surgery_name: string
  surgery_date?: string
  hospital?: string
  notes?: string
}

export interface VaccinationItem {
  id: number
  vaccine_name: string
  dose_no?: string
  vaccinated_date?: string
  facility?: string
}

export interface ProfileSummary {
  diagnoses: DiagnosisItem[]
  medications: MedicationItem[]
  allergies: AllergyItem[]
  lifestyles: LifestyleItem[]
  surgeries: SurgeryItem[]
  vaccinations: VaccinationItem[]
}

export const profileApi = {
  get: (memberId: number) =>
    request<ProfileSummary>(`/members/${memberId}/profile`),

  addDiagnosis: (memberId: number, data: { disease_name: string; severity?: string; diagnosed_date?: string; status?: string }) =>
    request<DiagnosisItem>(`/members/${memberId}/profile/diagnoses`, { method: 'POST', body: JSON.stringify(data) }),

  addMedication: (memberId: number, data: { drug_name: string; dosage: string; frequency: string; start_date?: string }) =>
    request<MedicationItem>(`/members/${memberId}/profile/medications`, { method: 'POST', body: JSON.stringify(data) }),

  addAllergy: (memberId: number, data: { type: string; name: string; severity?: string }) =>
    request<AllergyItem>(`/members/${memberId}/profile/allergies`, { method: 'POST', body: JSON.stringify(data) }),

  addLifestyle: (memberId: number, data: { category: string; status: string; frequency?: string; recorded_at?: string }) =>
    request<LifestyleItem>(`/members/${memberId}/profile/lifestyles`, { method: 'POST', body: JSON.stringify(data) }),

  addSurgery: (memberId: number, data: { surgery_name: string; surgery_date?: string; hospital?: string; notes?: string }) =>
    request<SurgeryItem>(`/members/${memberId}/profile/surgeries`, { method: 'POST', body: JSON.stringify(data) }),

  addVaccination: (memberId: number, data: { vaccine_name: string; dose_no?: string; vaccinated_date?: string; facility?: string }) =>
    request<VaccinationItem>(`/members/${memberId}/profile/vaccinations`, { method: 'POST', body: JSON.stringify(data) }),

  deleteRecord: (recordType: string, recordId: number) =>
    request<void>(`/members/profile/records/${recordType}/${recordId}`, { method: 'DELETE' }),
}

// ---- Report Extraction ----

export interface ExtractedMetric {
  metric_name: string
  label: string
  value: number | string
  unit?: string
  reference_lower?: number
  reference_upper?: number
  is_abnormal: boolean
}

export interface ExtractedDiagnosis {
  disease_name: string
  severity?: string
  diagnosed_date?: string
}

export interface ExtractedMedication {
  drug_name: string
  dosage: string
  frequency: string
}

export interface ExtractedLabTest {
  report_name: string
  test_name: string
  value: number | string
  unit?: string
  reference_lower?: number
  reference_upper?: number
  is_abnormal: boolean
}

export interface ExtractedExamFinding {
  finding_category: string
  finding_desc: string
  value_num?: number | string | null
  unit?: string
  conclusion?: string
}

export interface ExtractionResult {
  patient_name?: string
  report_type?: string
  report_date?: string
  metrics: ExtractedMetric[]
  diagnoses: ExtractedDiagnosis[]
  medications: ExtractedMedication[]
  lab_tests: ExtractedLabTest[]
  exam_findings: ExtractedExamFinding[]
  summary?: string
}

export interface ReportRecord {
  id: number
  member_id: number
  file_name: string
  file_type: string
  file_size: number
  source: string
  status: string  // uploaded / extracting / pending / archived / rejected / cancelled
  extraction?: ExtractionResult | null
  report_type?: string | null
  report_date?: string | null
  summary?: string | null
  patient_name?: string | null
  saved_metrics: number
  saved_diagnoses: number
  saved_medications: number
  saved_lab_tests: number
  saved_exam_findings: number
  created_at: string
  updated_at: string
}

export const reportsApi = {
  list: (memberId: number) =>
    request<ReportRecord[]>(`/members/${memberId}/reports`),

  get: (memberId: number, reportId: number) =>
    request<ReportRecord>(`/members/${memberId}/reports/${reportId}`),

  upload: async (memberId: number, file: File, source: string = 'report_page'): Promise<ReportRecord> => {
    const formData = new FormData()
    formData.append('file', file)
    const params = new URLSearchParams({ source })
    const res = await fetch(`${BASE_URL}/members/${memberId}/reports/upload?${params}`, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      throw new ApiError(body.detail ?? `HTTP ${res.status}`, res.status)
    }
    return res.json()
  },

  confirm: (memberId: number, reportId: number, data: {
    extraction: ExtractionResult
    keep_metric_indices?: number[]
    keep_diagnosis_indices?: number[]
    keep_medication_indices?: number[]
    keep_lab_test_indices?: number[]
    keep_exam_finding_indices?: number[]
  }) =>
    request<{ saved_metrics: number; saved_diagnoses: number; saved_medications: number; saved_lab_tests: number; saved_exam_findings: number }>(
      `/members/${memberId}/reports/${reportId}/confirm`,
      { method: 'POST', body: JSON.stringify(data) },
    ),

  delete: (memberId: number, reportId: number) =>
    request<{ ok: boolean }>(`/members/${memberId}/reports/${reportId}`, { method: 'DELETE' }),

  retry: (memberId: number, reportId: number) =>
    request<ReportRecord>(`/members/${memberId}/reports/${reportId}/retry`, { method: 'POST' }),

  cancel: (memberId: number, reportId: number) =>
    request<ReportRecord>(`/members/${memberId}/reports/${reportId}/cancel`, { method: 'POST' }),
}

// ---- Checkup Recommendation ----

export interface Completeness {
  score: number
  level: string
  missing_fields: string[]
}

export interface ProfileCheckResponse {
  completeness: Completeness
}

export interface SupplementResponse {
  updated: boolean
  completeness: Completeness
}

export interface RecommendResponse {
  content: string
  completeness: Completeness
}

export interface SupplementPayload {
  region?: string
  occupation?: string
  is_pregnant?: string
  is_preparing_pregnancy?: string
  has_sexual_history?: string
  contrast_allergy?: string
  has_pacemaker?: string
  has_metal_implant?: string
  on_anticoagulant?: string
  claustrophobia?: string
  is_breastfeeding?: string
  has_coagulopathy?: string
  has_heart_failure?: string
}

export const checkupApi = {
  profileCheck: (memberId: number) =>
    request<ProfileCheckResponse>(`/members/${memberId}/checkup-profile-check`),

  supplement: (memberId: number, data: SupplementPayload) =>
    request<SupplementResponse>(`/members/${memberId}/checkup-supplement`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

 recommend: (memberId: number, budgetTier: string) =>
   request<RecommendResponse>(`/members/${memberId}/checkup-recommend`, {
     method: 'POST',
     body: JSON.stringify({ budget_tier: budgetTier }),
   }),
 
 getLatest: (memberId: number) =>
   request<RecommendResponse | null>(`/members/${memberId}/checkup-latest`),
}

// ---- Settings ----

export interface ProviderConfig {
  base_url: string
  api_key: string
  model: string
  is_configured: boolean
}

export interface ProviderConfigResponse {
  multimodal_api: ProviderConfig
  text_api: ProviderConfig
  local_llm: ProviderConfig
  text_provider_priority: string
}

export interface ProviderHealthResult {
  status: string
  latency_ms?: number
  error?: string
}

export const settingsApi = {
  getProviders: () =>
    request<ProviderConfigResponse>('/settings/providers'),

  checkHealth: () =>
    request<Record<string, ProviderHealthResult>>('/settings/providers/health'),

  exportData: () =>
    fetch(`${BASE_URL}/settings/export`).then(async (res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.blob()
    }),

  wipeData: () =>
    request<{ deleted: boolean; message: string }>('/settings/data?confirm=DELETE', {
      method: 'DELETE',
    }),

  updateProviders: (data: ProviderUpdatePayload) =>
    request<{ updated: boolean; fields: string[]; message: string }>('/settings/providers', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
}

export interface ProviderUpdatePayload {
  multimodal_api_base?: string
  multimodal_api_key?: string
  multimodal_api_model?: string
  text_api_base?: string
  text_api_key?: string
  text_api_model?: string
  local_llm_base?: string
  local_llm_model?: string
  text_provider_priority?: string
}

export interface FeishuChannel {
  id: number
  name: string
  app_id: string
  app_secret_masked: string
  member_id: number | null
  member_name: string | null
  is_active: boolean
  connected: boolean
}

export interface FeishuChannelCreate {
  name: string
  app_id: string
  app_secret: string
  member_id?: number | null
  is_active?: boolean
}

export interface FeishuChannelUpdate {
  name?: string
  app_id?: string
  app_secret?: string
  member_id?: number | null
  is_active?: boolean
}

export const feishuApi = {
  listChannels: () => request<FeishuChannel[]>('/feishu/channels'),
  createChannel: (data: FeishuChannelCreate) =>
    request<FeishuChannel>('/feishu/channels', { method: 'POST', body: JSON.stringify(data) }),
  updateChannel: (id: number, data: FeishuChannelUpdate) =>
    request<FeishuChannel>(`/feishu/channels/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteChannel: (id: number) =>
    request<{ deleted: boolean; id: number }>(`/feishu/channels/${id}`, { method: 'DELETE' }),
  reload: () => request<{ ok: boolean; connections: any[] }>('/feishu/reload', { method: 'POST' }),
}

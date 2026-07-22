// Health profile domain types, aligned with backend schema (OpenSpec health-profile spec)

export type Gender = 'male' | 'female' | 'other'

export type BloodType = 'A' | 'B' | 'AB' | 'O' | 'unknown'

export type Relationship =
  | 'self'
  | 'spouse'
  | 'parent'
  | 'child'
  | 'sibling'
  | 'grandparent'
  | 'other'

// Field family A: basic info
export interface FamilyMember {
  id: string
  name: string
  gender: Gender
  birth_date: string // ISO date
  relationship: Relationship
  blood_type?: BloodType
  phone?: string
  avatar_url?: string
  created_at: string
  updated_at: string
}

export type FamilyMemberInput = Omit<FamilyMember, 'id' | 'created_at' | 'updated_at'>

// Data source tracing (field family H)
export type SourceType = 'manual' | 'report' | 'chat_extract'

// Field family B: physiological metrics
export type MetricName =
  | 'blood_pressure_systolic'
  | 'blood_pressure_diastolic'
  | 'heart_rate'
  | 'blood_glucose'
  | 'weight'
  | 'height'
  | 'bmi'
  | 'temperature'
  | 'spo2'
  | 'steps'

export type MetricUnit = string

export interface MetricRecord {
  id: number
  member_id: number
  metric_name: string
  value: number
  unit: string
  reference_lower?: number
  reference_upper?: number
  is_abnormal: boolean
  is_critical: boolean
  measured_at: string // ISO datetime
  context?: string
  source_type: SourceType
  created_at: string
}

export interface MetricRecordInput {
  metric_name: string
  value: number
  unit: string
  measured_at: string
  reference_lower?: number
  reference_upper?: number
  context?: string
  source_type: SourceType
}

// Field family C: diagnosis
export interface DiagnosisRecord {
  id: string
  member_id: string
  name: string
  icd_code?: string
  diagnosed_date: string
  severity?: string
  source_type: SourceType
  source_ref?: string
  note?: string
  created_at: string
}

// Field family D: medication
export interface MedicationRecord {
  id: string
  member_id: string
  drug_name: string
  dosage: string
  frequency: string
  start_date: string
  end_date?: string
  source_type: SourceType
  note?: string
  created_at: string
}

// Field family E: allergy
export interface AllergyRecord {
  id: string
  member_id: string
  allergen: string
  reaction: string
  severity: 'mild' | 'moderate' | 'severe'
  source_type: SourceType
  note?: string
  created_at: string
}

// Generic API response wrapper
export interface ApiResponse<T> {
  data: T
  message?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// ===== Chat =====
export type RiskLevel = 'S' | 'A' | 'B' | null

export interface ToolCallRecord {
  name: string
  arguments?: string
  result?: unknown
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  tool_calls?: ToolCallRecord[]
  risk_level?: RiskLevel
  isHighRiskAlert?: boolean
}

export interface ChatResponse {
  reply: string
  tool_calls?: ToolCallRecord[]
  risk_level?: RiskLevel
  isHighRiskAlert?: boolean
}

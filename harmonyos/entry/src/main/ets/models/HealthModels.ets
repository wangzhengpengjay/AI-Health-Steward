/**
 * 健康管家数据模型 — 对齐后端 PostgreSQL schema
 * 
 * 所有模型使用 ArkData RDB (SQLite) 存储，SQL 语法与 PostgreSQL 基本兼容
 * 
 * ArkTS 限制：
 * - 不支持 Record<K,V>，使用 Map<K,V> 或直接定义 interface
 * - 不支持 object 作为类型，需要显式 interface
 */

// ============================================================
// 基础类型
// ============================================================

export type RiskLevel = 'S' | 'A' | 'B';
export type MessageSource = 'webui' | 'proactive' | 'system';
export type MessageType = 'normal' | 'proactive' | 'followup';
export type Priority = 'critical' | 'high' | 'normal' | 'low';
export type TaskCategory = 'recheck' | 'medication' | 'lifestyle' | 'visit' | 'other';
export type TaskUrgency = 'critical' | 'urgent' | 'normal' | 'low';

// ============================================================
// 家庭成员
// ============================================================

export interface FamilyMember {
  id: number;
  name: string;
  gender: string;
  birth_date: string;
  height: number;
  weight: number;
  bmi: number;
  blood_type: string;
  relationship: string;
  region: string;
  occupation: string;
  is_pregnant: boolean;
  is_preparing_pregnancy: boolean;
  has_sexual_history: boolean;
  contrast_allergy: boolean;
  has_pacemaker: boolean;
  has_metal_implant: boolean;
  egfr: number | null;
  on_anticoagulant: boolean;
  claustrophobia: boolean;
  is_breathing: boolean;
  has_coagulopathy: boolean;
  has_heart_failure: boolean;
  created_at: string;
  updated_at: string;
  memory_summary: string | null;
  memory_summary_updated_at: string | null;
}

// ============================================================
// 指标记录
// ============================================================

export interface MetricRecord {
  id: number;
  member_id: number;
  metric_name: string;
  value: number | null;
  text_value: string | null;
  unit: string;
  reference_lower: number | null;
  reference_upper: number | null;
  is_abnormal: boolean;
  is_critical: boolean;
  measured_at: string;
  context: string | null;
  source_type: string;
  created_at: string;
}

// ============================================================
// 诊断/用药/过敏/生活方式/家族史/手术/疫苗
// ============================================================

export interface Diagnosis {
  id: number;
  member_id: number;
  diagnosis_name: string;
  diagnosis_date: string;
  hospital: string | null;
  notes: string | null;
  created_at: string;
}

export interface Medication {
  id: number;
  member_id: number;
  drug_name: string;
  generic_name: string | null;
  dosage: string;
  frequency: string;
  route: string | null;
  start_date: string;
  end_date: string | null;
  diagnosis_id: number | null;
  created_at: string;
}

export interface Allergy {
  id: number;
  member_id: number;
  type: string;
  name: string;
  severity: string | null;
  recorded_at: string;
  created_at: string;
}

export interface Lifestyle {
  id: number;
  member_id: number;
  category: string;
  status: string;
  frequency: string | null;
  recorded_at: string;
  created_at: string;
}

export interface FamilyHistory {
  id: number;
  member_id: number;
  relation: string;
  disease_name: string;
  recorded_at: string;
  created_at: string;
}

export interface Surgery {
  id: number;
  member_id: number;
  surgery_name: string;
  surgery_date: string;
  hospital: string | null;
  notes: string | null;
  created_at: string;
}

export interface Vaccination {
  id: number;
  member_id: number;
  vaccine_name: string;
  dose_no: number;
  vaccinated_date: string;
  facility: string | null;
  created_at: string;
}

// ============================================================
// 聊天消息
// ============================================================

export interface ChatMessageMetadata {
  tool_calls?: string[];
  risk_level?: string;
}

export interface ChatMessage {
  id: number;
  member_id: number;
  role: string;
  content: string;
  source: MessageSource;
  message_type: MessageType;
  metadata: ChatMessageMetadata | null;
  created_at: string;
}

// ============================================================
// 健康任务
// ============================================================

export interface HealthTask {
  id: number;
  member_id: number;
  title: string;
  description: string;
  category: TaskCategory;
  urgency: TaskUrgency;
  due_date: string | null;
  status: string;
  source: string;
  source_ref: string | null;
  auto_generated: boolean;
  completed_at: string | null;
  dismissed_at: string | null;
  postponed_count: number;
  created_at: string;
  updated_at: string;
}

// ============================================================
// 体检报告 / 健康小结
// ============================================================

export interface CheckupReport {
  id: number;
  member_id: number;
  report_date: string;
  hospital: string | null;
  report_type: string | null;
  raw_text: string | null;
  extraction_json: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface HealthSummary {
  id: number;
  member_id: number;
  period: string;
  period_start: string;
  period_end: string;
  content: string;
  created_at: string;
}

// ============================================================
// 主动巡检
// ============================================================

export interface PatrolResult {
  should_push: boolean;
  message: string;
  priority: Priority;
  tasks: PatrolTask[];
  patrol_id: string;
}

export interface PatrolTask {
  title: string;
  description: string;
  category: TaskCategory;
  urgency: TaskUrgency;
  due_date: string | null;
}

// ============================================================
// LLM 对话
// ============================================================

export interface LLMToolCallFunction {
  name: string;
  arguments: string;
}

export interface LLMToolCall {
  id: string;
  type: string;
  function: LLMToolCallFunction;
}

export interface LLMMessage {
  role: string;
  content: string;
  tool_calls?: LLMToolCall[];
  tool_call_id?: string;
  name?: string;
}

export interface LLMResponse {
  content: string;
  tool_calls: LLMToolCall[] | null;
  finish_reason: string;
}

// ============================================================
// 代理提醒
// ============================================================

export interface ReminderInfo {
  reminderId: number;
  title: string;
  content: string;
  scheduledTime: string;
  memberId: number;
  taskId: number | null;
}

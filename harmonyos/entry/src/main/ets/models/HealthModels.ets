/**
 * 健康管家数据模型 — 对齐后端 PostgreSQL schema
 * 
 * 所有模型使用 ArkData RDB (SQLite) 存储，SQL 语法与 PostgreSQL 基本兼容
 */

// ============================================================
// 基础类型
// ============================================================

/** 风险级别 */
export type RiskLevel = 'S' | 'A' | 'B';

/** 消息来源 */
export type MessageSource = 'webui' | 'proactive' | 'system';

/** 消息类型 */
export type MessageType = 'normal' | 'proactive' | 'followup';

/** 优先级 */
export type Priority = 'critical' | 'high' | 'normal' | 'low';

// ============================================================
// 家庭成员
// ============================================================

export interface FamilyMember {
  id: number;
  name: string;
  gender: string;        // 'male' | 'female'
  birth_date: string;    // ISO date
  height: number;        // cm
  weight: number;        // kg
  bmi: number;           // 自动计算
  blood_type: string;    // A/B/AB/O + Rh+/-
  relationship: string;  // self/parent/child/spouse/other
  region: string;
  occupation: string;
  // 健康标记
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
  // 长期记忆摘要
  memory_summary: string | null;
  memory_summary_updated_at: string | null;
}

// ============================================================
// 指标记录
// ============================================================

export interface MetricRecord {
  id: number;
  member_id: number;
  metric_name: string;     // blood_pressure_systolic, blood_pressure_diastolic, glucose, etc.
  value: number | null;
  text_value: string | null;  // 文本型值 (如 "阴性")
  unit: string;
  reference_lower: number | null;
  reference_upper: number | null;
  is_abnormal: boolean;
  is_critical: boolean;
  measured_at: string;     // ISO datetime
  context: string | null;  // 空腹/餐后/等
  source_type: string;     // 'manual' | 'chat_extract' | 'report'
  created_at: string;
}

// ============================================================
// 诊断记录
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

// ============================================================
// 用药记录
// ============================================================

export interface Medication {
  id: number;
  member_id: number;
  drug_name: string;
  generic_name: string | null;
  dosage: string;           // "5mg"
  frequency: string;        // "每日一次"
  route: string | null;     // "口服"
  start_date: string;
  end_date: string | null;
  diagnosis_id: number | null;
  created_at: string;
}

// ============================================================
// 过敏记录
// ============================================================

export interface Allergy {
  id: number;
  member_id: number;
  type: string;             // 'drug' | 'food' | 'environmental'
  name: string;
  severity: string | null;  // 'mild' | 'moderate' | 'severe'
  recorded_at: string;
  created_at: string;
}

// ============================================================
// 生活方式
// ============================================================

export interface Lifestyle {
  id: number;
  member_id: number;
  category: string;         // 'smoking' | 'drinking' | 'exercise' | 'sleep' | 'diet'
  status: string;            // 'current' | 'quit' | 'never' | 'occasional'
  frequency: string | null;
  recorded_at: string;
  created_at: string;
}

// ============================================================
// 家族史
// ============================================================

export interface FamilyHistory {
  id: number;
  member_id: number;
  relation: string;          // 'father' | 'mother' | 'sibling' | etc.
  disease_name: string;
  recorded_at: string;
  created_at: string;
}

// ============================================================
// 手术记录
// ============================================================

export interface Surgery {
  id: number;
  member_id: number;
  surgery_name: string;
  surgery_date: string;
  hospital: string | null;
  notes: string | null;
  created_at: string;
}

// ============================================================
// 疫苗接种
// ============================================================

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

export interface ChatMessage {
  id: number;
  member_id: number;
  role: string;              // 'user' | 'assistant'
  content: string;
  source: MessageSource;
  message_type: MessageType;
  metadata: Record<string, object> | null;  // JSON metadata
  created_at: string;
}

// ============================================================
// 健康任务
// ============================================================

export type TaskCategory = 'recheck' | 'medication' | 'lifestyle' | 'visit' | 'other';
export type TaskUrgency = 'critical' | 'urgent' | 'normal' | 'low';

export interface HealthTask {
  id: number;
  member_id: number;
  title: string;
  description: string;
  category: TaskCategory;
  urgency: TaskUrgency;
  due_date: string | null;
  status: string;            // 'open' | 'completed' | 'dismissed'
  source: string;            // 'metric' | 'diagnosis' | 'manual' | 'proactive'
  source_ref: string | null;
  auto_generated: boolean;
  completed_at: string | null;
  dismissed_at: string | null;
  postponed_count: number;
  created_at: string;
  updated_at: string;
}

// ============================================================
// 体检报告
// ============================================================

export interface CheckupReport {
  id: number;
  member_id: number;
  report_date: string;
  hospital: string | null;
  report_type: string | null;
  raw_text: string | null;
  extraction_json: string | null;
  status: string;            // 'pending' | 'processing' | 'completed' | 'failed'
  created_at: string;
  updated_at: string;
}

// ============================================================
// 健康小结
// ============================================================

export interface HealthSummary {
  id: number;
  member_id: number;
  period: string;            // 'weekly' | 'monthly' | 'yearly'
  period_start: string;
  period_end: string;
  content: string;
  created_at: string;
}

// ============================================================
// 主动巡检结果
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
// LLM 对话消息（发送给云端 LLM 的格式）
// ============================================================

export interface LLMMessage {
  role: string;              // 'system' | 'user' | 'assistant' | 'tool'
  content: string;
  tool_calls?: object[];
  tool_call_id?: string;
  name?: string;
}

export interface LLMResponse {
  content: string;
  tool_calls: LLMToolCall[] | null;
  finish_reason: string;
}

export interface LLMToolCall {
  id: string;
  name: string;
  arguments: string;         // JSON string
}

// ============================================================
// 代理提醒（Reminder Agent）
// ============================================================

export interface ReminderInfo {
  reminderId: number;
  title: string;
  content: string;
  scheduledTime: string;
  memberId: number;
  taskId: number | null;
}

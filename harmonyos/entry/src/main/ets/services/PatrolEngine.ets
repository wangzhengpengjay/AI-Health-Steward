/**
 * 主动健康巡检引擎（ArkTS 版）
 * 
 * 对齐后端 patrol_engine.py 逻辑：
 * 1. 加载成员完整画像
 * 2. 规则层扫描（异常指标、到期待办等）
 * 3. AI 层推理（LLM 综合画像判断是否需要干预）
 * 4. 输出：主动消息（推送）或 静默记录（不推送）
 */

import { DatabaseService } from './DatabaseService';
import { LLMClient, HEALTH_TOOLS } from './LLMClient';
import { ChatMessage, PatrolResult, PatrolTask, Priority, HealthTask } from '../models/HealthModels';

// ============================================================
// 规则层：参考范围
// ============================================================

interface MetricRule {
  name: string;
  critical_low: number | null;
  critical_high: number | null;
  abnormal_low: number | null;
  abnormal_high: number | null;
  unit: string;
}

const CRITICAL_RULES: MetricRule[] = [
  { name: 'blood_pressure_systolic', critical_low: 90, critical_high: 180, abnormal_low: 120, abnormal_high: 140, unit: 'mmHg' },
  { name: 'blood_pressure_diastolic', critical_low: 60, critical_high: 120, abnormal_low: 80, abnormal_high: 90, unit: 'mmHg' },
  { name: 'glucose_fasting', critical_low: 2.8, critical_high: 16.7, abnormal_low: 3.9, abnormal_high: 6.1, unit: 'mmol/L' },
  { name: 'glucose_random', critical_low: 2.8, critical_high: 16.7, abnormal_low: 3.9, abnormal_high: 11.1, unit: 'mmol/L' },
  { name: 'heart_rate', critical_low: 40, critical_high: 150, abnormal_low: 60, abnormal_high: 100, unit: 'bpm' },
  { name: 'temperature', critical_low: 35.0, critical_high: 40.0, abnormal_low: 36.0, abnormal_high: 37.3, unit: '°C' },
  { name: 'spo2', critical_low: 88, critical_high: null, abnormal_low: 95, abnormal_high: null, unit: '%' },
];

// ============================================================
// 打扰规则：频率控制
// ============================================================

const FREQUENCY_LIMITS: Record<string, number> = {
  critical: 0,   // 不限
  high: 1,        // 每周1次
  normal: 1,      // 每天1次
  low: 0,         // 不推送
};

// ============================================================
// 巡检引擎
// ============================================================

export class PatrolEngine {
  private db: DatabaseService;
  private llm: LLMClient;

  constructor(db: DatabaseService, llm: LLMClient) {
    this.db = db;
    this.llm = llm;
  }

  /**
   * 巡检单个成员
   * @param memberId 成员ID
   * @param trigger 触发来源：scheduled | event:abnormal_metric | event:task_due
   * @returns 巡检结果
   */
  async patrolMember(memberId: number, trigger: string): Promise<PatrolResult> {
    console.info(`[PatrolEngine] Patrolling member ${memberId}, trigger=${trigger}`);

    // 1. 构建画像快照
    const snapshot = await this.buildHealthSnapshot(memberId);
    
    // 2. 规则层扫描
    const ruleAlerts = this.scanRules(snapshot);
    
    // 3. 如果规则层发现危急值，直接生成紧急消息
    if (ruleAlerts.critical.length > 0) {
      const message = this.formatCriticalMessage(ruleAlerts.critical);
      const tasks = this.generateTasksFromAlerts(ruleAlerts.critical, 'critical');
      return {
        should_push: true,
        message,
        priority: 'critical',
        tasks,
        patrol_id: `patrol_${Date.now()}_${memberId}`,
      };
    }

    // 4. AI 层推理
    const aiResult = await this.aiInference(snapshot, ruleAlerts.abnormal);
    
    // 5. 频率控制
    if (aiResult.should_push) {
      const allowed = await this.checkFrequency(memberId, aiResult.priority);
      if (!allowed) {
        return {
          should_push: false,
          message: '',
          priority: 'low',
          tasks: [],
          patrol_id: `patrol_${Date.now()}_${memberId}`,
        };
      }
    }

    return aiResult;
  }

  /**
   * 构建成员健康画像快照
   */
  private async buildHealthSnapshot(memberId: number): Promise<HealthSnapshot> {
    const db = this.db.getStore();

    // 基本信息
    const memberRs = await this.db.query(
      `SELECT * FROM family_members WHERE id = ? AND is_deleted = 0`,
      [String(memberId)]
    );
    const memberRows = this.db.resultSetToArray(memberRs);
    const member = memberRows[0] || {};

    // 最近指标（最近30天）
    const metricsRs = await this.db.query(
      `SELECT * FROM metric_records WHERE member_id = ? AND measured_at >= datetime('now', '-30 days') ORDER BY measured_at DESC`,
      [String(memberId)]
    );
    const metrics = this.db.resultSetToArray(metricsRs);

    // 异常指标
    const abnormalRs = await this.db.query(
      `SELECT * FROM metric_records WHERE member_id = ? AND is_abnormal = 1 ORDER BY measured_at DESC LIMIT 10`,
      [String(memberId)]
    );
    const abnormal = this.db.resultSetToArray(abnormalRs);

    // 诊断
    const diagRs = await this.db.query(
      `SELECT * FROM diagnoses WHERE member_id = ? ORDER BY created_at DESC`,
      [String(memberId)]
    );
    const diagnoses = this.db.resultSetToArray(diagRs);

    // 用药
    const medRs = await this.db.query(
      `SELECT * FROM medications WHERE member_id = ? ORDER BY created_at DESC`,
      [String(memberId)]
    );
    const medications = this.db.resultSetToArray(medRs);

    // 待办任务
    const taskRs = await this.db.query(
      `SELECT * FROM health_tasks WHERE member_id = ? AND status = 'open' ORDER BY due_date ASC`,
      [String(memberId)]
    );
    const tasks = this.db.resultSetToArray(taskRs);

    // 长期记忆
    const memorySummary = member['memory_summary'] as string || '';

    return {
      member,
      recentMetrics: metrics,
      abnormalMetrics: abnormal,
      diagnoses,
      medications,
      openTasks: tasks,
      memorySummary,
    };
  }

  /**
   * 规则层扫描
   */
  private scanRules(snapshot: HealthSnapshot): { critical: RuleAlert[]; abnormal: RuleAlert[] } {
    const critical: RuleAlert[] = [];
    const abnormal: RuleAlert[] = [];

    for (const metric of snapshot.recentMetrics) {
      const rule = CRITICAL_RULES.find(r => r.name === metric['metric_name']);
      if (!rule) continue;

      const value = metric['value'] as number;
      if (value == null) continue;

      // 危急值
      if ((rule.critical_high != null && value >= rule.critical_high) ||
          (rule.critical_low != null && value <= rule.critical_low)) {
        critical.push({
          metric_name: metric['metric_name'] as string,
          value,
          unit: rule.unit,
          level: 'critical',
          message: `${metric['metric_name']} ${value}${rule.unit} 达到危急值`,
        });
      }
      // 异常值
      else if ((rule.abnormal_high != null && value >= rule.abnormal_high) ||
               (rule.abnormal_low != null && value <= rule.abnormal_low)) {
        abnormal.push({
          metric_name: metric['metric_name'] as string,
          value,
          unit: rule.unit,
          level: 'abnormal',
          message: `${metric['metric_name']} ${value}${rule.unit} 偏高/偏低`,
        });
      }
    }

    // 到期待办
    for (const task of snapshot.openTasks) {
      const dueDate = task['due_date'] as string;
      if (dueDate) {
        const due = new Date(dueDate);
        const now = new Date();
        if (due <= now) {
          abnormal.push({
            metric_name: 'task_due',
            value: 0,
            unit: '',
            level: 'abnormal',
            message: `待办"${task['title']}"已到期`,
          });
        }
      }
    }

    return { critical, abnormal };
  }

  /**
   * AI 层推理
   */
  private async aiInference(
    snapshot: HealthSnapshot,
    abnormalAlerts: RuleAlert[],
  ): Promise<PatrolResult> {
    const patrolId = `patrol_${Date.now()}_${snapshot.member['id']}`;

    // 构建画像摘要
    const profileText = this.formatSnapshotForAI(snapshot, abnormalAlerts);

    const messages = [
      {
        role: 'system',
        content: `你是一个主动健康管家。根据用户的健康画像，判断是否需要主动干预。

输出格式（严格 JSON）：
{
  "should_push": true/false,
  "priority": "critical" | "high" | "normal" | "low",
  "message": "主动消息内容（如果push）",
  "tasks": [
    {"title": "任务标题", "description": "描述", "category": "recheck", "urgency": "normal", "due_date": null}
  ]
}

判断原则：
- 危急值 → critical，立即推送
- 异常持续恶化 → high，每周最多1次
- 待办到期 → normal，每天最多1次
- 无异常 → low，不推送
- 消息要口语化、关心式，不要像系统通知`,
      },
      {
        role: 'user',
        content: profileText,
      },
    ];

    try {
      const response = await this.llm.chat(messages, undefined, 0.3, 800);
      const result = JSON.parse(response.content);
      
      return {
        should_push: result.should_push ?? false,
        message: result.message ?? '',
        priority: result.priority ?? 'low',
        tasks: result.tasks ?? [],
        patrol_id: patrolId,
      };
    } catch (e) {
      console.error('[PatrolEngine] AI inference failed:', e);
      // 规则兜底：有异常但不推
      return {
        should_push: false,
        message: '',
        priority: 'low',
        tasks: [],
        patrol_id: patrolId,
      };
    }
  }

  /**
   * 频率控制
   */
  private async checkFrequency(memberId: number, priority: Priority): Promise<boolean> {
    if (priority === 'critical') return true;  // 危急不限
    if (priority === 'low') return false;     // 低优先级不推

    const limit = FREQUENCY_LIMITS[priority] || 0;
    if (limit === 0) return false;

    // 查询近期推送次数
    const period = priority === 'high' ? "-7 days" : "-1 days";
    const rs = await this.db.query(
      `SELECT COUNT(*) as count FROM chat_messages WHERE member_id = ? AND source = 'proactive' AND created_at >= datetime('now', ?)`,
      [String(memberId), period]
    );
    const rows = this.db.resultSetToArray(rs);
    const count = rows[0]?.['count'] as number || 0;

    return count < limit;
  }

  /**
   * 保存主动消息到数据库
   */
  async saveProactiveMessage(memberId: number, message: string, priority: Priority, patrolId: string): Promise<number> {
    const metadata = JSON.stringify({ priority, patrol_id: patrolId });
    return await this.db.insert('chat_messages', {
      member_id: memberId,
      role: 'assistant',
      content: message,
      source: 'proactive',
      message_type: 'proactive',
      metadata_json: metadata,
    });
  }

  /**
   * 从巡检结果生成任务并保存
   */
  async saveTasks(memberId: number, tasks: PatrolTask[]): Promise<number[]> {
    const taskIds: number[] = [];
    for (const task of tasks) {
      const id = await this.db.insert('health_tasks', {
        member_id: memberId,
        title: task.title,
        description: task.description,
        category: task.category,
        urgency: task.urgency,
        due_date: task.due_date,
        status: 'open',
        source: 'proactive',
        auto_generated: 1,
      });
      taskIds.push(id);
    }
    return taskIds;
  }

  // ============================================================
  // 格式化辅助
  // ============================================================

  private formatCriticalMessage(alerts: RuleAlert[]): string {
    const lines = alerts.map(a => `🚨 ${a.message}`);
    return `${lines.join('\n')}\n\n这是危急值，请立即就医。`;
  }

  private formatSnapshotForAI(snapshot: HealthSnapshot, abnormalAlerts: RuleAlert[]): string {
    const m = snapshot.member;
    const parts: string[] = [];

    parts.push(`成员：${m['name'] || '未知'}，${m['gender'] || ''}，${m['birth_date'] || ''}出生`);
    
    if (snapshot.diagnoses.length > 0) {
      parts.push(`诊断：${snapshot.diagnoses.map((d: Record<string, object>) => d['diagnosis_name']).join('、')}`);
    }
    
    if (snapshot.medications.length > 0) {
      parts.push(`用药：${snapshot.medications.map((med: Record<string, object>) => `${med['drug_name']} ${med['dosage']} ${med['frequency']}`).join('；')}`);
    }

    if (snapshot.recentMetrics.length > 0) {
      const recent = snapshot.recentMetrics.slice(0, 10);
      parts.push(`近期指标：${recent.map((mt: Record<string, object>) => `${mt['metric_name']}=${mt['value']}${mt['unit']}`).join('，')}`);
    }

    if (abnormalAlerts.length > 0) {
      parts.push(`异常项：${abnormalAlerts.map(a => a.message).join('；')}`);
    }

    if (snapshot.openTasks.length > 0) {
      parts.push(`待办：${snapshot.openTasks.map((t: Record<string, object>) => t['title']).join('、')}`);
    }

    if (snapshot.memorySummary) {
      parts.push(`记忆摘要：${snapshot.memorySummary}`);
    }

    return parts.join('\n');
  }

  private generateTasksFromAlerts(alerts: RuleAlert[], urgency: string): PatrolTask[] {
    return alerts.map(a => ({
      title: `${a.metric_name}复查`,
      description: a.message,
      category: 'recheck',
      urgency: urgency,
      due_date: new Date(Date.now() + 86400000).toISOString().split('T')[0], // 明天
    }));
  }
}

// ============================================================
// 内部类型
// ============================================================

interface HealthSnapshot {
  member: Record<string, object>;
  recentMetrics: Record<string, object>[];
  abnormalMetrics: Record<string, object>[];
  diagnoses: Record<string, object>[];
  medications: Record<string, object>[];
  openTasks: Record<string, object>[];
  memorySummary: string;
}

interface RuleAlert {
  metric_name: string;
  value: number;
  unit: string;
  level: 'critical' | 'abnormal';
  message: string;
}

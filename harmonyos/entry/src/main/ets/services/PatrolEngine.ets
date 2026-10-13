/**
 * 主动健康巡检引擎（ArkTS 版）
 * 
 * ArkTS 核心限制：
 * - 不支持索引签名 → DataRow 是 Map<string, ColumnValue>
 * - 不支持 row['key'] → 使用 row.get('key')
 * - 不支持 object 类型 → 使用具体 interface
 */

import { relationalStore } from '@kit.ArkData';
import { DatabaseService, DataRow, ColumnValue, getMapVal, getMapString, getMapNumber } from './DatabaseService';
import { LLMClient } from './LLMClient';
import { PatrolResult, PatrolTask, Priority, TaskCategory, TaskUrgency } from '../models/HealthModels';

// ============================================================
// 规则层 & 内部类型
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

interface HealthSnapshot {
  member: DataRow;
  recentMetrics: DataRow[];
  abnormalMetrics: DataRow[];
  diagnoses: DataRow[];
  medications: DataRow[];
  openTasks: DataRow[];
  memorySummary: string;
}

interface RuleAlert {
  metric_name: string;
  value: number;
  unit: string;
  level: number;
  message: string;
}

interface AITaskJSON {
  title: string;
  description: string;
  category: string;
  urgency: string;
  due_date: string;
}

interface AIResultJSON {
  should_push: boolean;
  priority: string;
  message: string;
  tasks: AITaskJSON[];
}

interface LLMMsg {
  role: string;
  content: string;
}

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

  async patrolMember(memberId: number, trigger: string): Promise<PatrolResult> {
    console.info(`[PatrolEngine] Patrolling member ${memberId}, trigger=${trigger}`);

    const snapshot: HealthSnapshot = await this.buildHealthSnapshot(memberId);

    const critical: RuleAlert[] = [];
    const abnormal: RuleAlert[] = [];
    this.scanRules(snapshot, critical, abnormal);

    if (critical.length > 0) {
      const message: string = this.formatCriticalMessage(critical);
      const tasks: PatrolTask[] = this.generateTasksFromAlerts(critical, 'critical');
      return {
        should_push: true,
        message: message,
        priority: 'critical',
        tasks: tasks,
        patrol_id: `patrol_${Date.now()}_${memberId}`,
      };
    }

    const aiResult: PatrolResult = await this.aiInference(snapshot, abnormal, memberId);

    if (aiResult.should_push) {
      const allowed: boolean = await this.checkFrequency(memberId, aiResult.priority);
      if (!allowed) {
        return {
          should_push: false,
          message: '',
          priority: 'low',
          tasks: [],
          patrol_id: aiResult.patrol_id,
        };
      }
    }

    return aiResult;
  }

  private async buildHealthSnapshot(memberId: number): Promise<HealthSnapshot> {
    const memberRs = await this.db.query(
      `SELECT * FROM family_members WHERE id = ? AND is_deleted = 0`,
      [String(memberId)]
    );
    const memberRows: DataRow[] = await this.db.resultSetToArray(memberRs);
    const member: DataRow = memberRows.length > 0 ? memberRows[0] : new Map<string, ColumnValue>();

    const metricsRs = await this.db.query(
      `SELECT * FROM metric_records WHERE member_id = ? AND measured_at >= datetime('now', '-30 days') ORDER BY measured_at DESC`,
      [String(memberId)]
    );
    const recentMetrics: DataRow[] = await this.db.resultSetToArray(metricsRs);

    const abnormalRs = await this.db.query(
      `SELECT * FROM metric_records WHERE member_id = ? AND is_abnormal = 1 ORDER BY measured_at DESC LIMIT 10`,
      [String(memberId)]
    );
    const abnormalMetrics: DataRow[] = await this.db.resultSetToArray(abnormalRs);

    const diagRs = await this.db.query(
      `SELECT * FROM diagnoses WHERE member_id = ? ORDER BY created_at DESC`,
      [String(memberId)]
    );
    const diagnoses: DataRow[] = await this.db.resultSetToArray(diagRs);

    const medRs = await this.db.query(
      `SELECT * FROM medications WHERE member_id = ? ORDER BY created_at DESC`,
      [String(memberId)]
    );
    const medications: DataRow[] = await this.db.resultSetToArray(medRs);

    const taskRs = await this.db.query(
      `SELECT * FROM health_tasks WHERE member_id = ? AND status = 'open' ORDER BY due_date ASC`,
      [String(memberId)]
    );
    const openTasks: DataRow[] = await this.db.resultSetToArray(taskRs);

    const memorySummary: string = getMapString(member, 'memory_summary');

    return {
      member: member,
      recentMetrics: recentMetrics,
      abnormalMetrics: abnormalMetrics,
      diagnoses: diagnoses,
      medications: medications,
      openTasks: openTasks,
      memorySummary: memorySummary,
    };
  }

  private scanRules(snapshot: HealthSnapshot, critical: RuleAlert[], abnormal: RuleAlert[]): void {
    for (const row of snapshot.recentMetrics) {
      const metricName: string = getMapString(row, 'metric_name');
      if (metricName.length === 0) {
        continue;
      }

      let rule: MetricRule | undefined;
      for (const r of CRITICAL_RULES) {
        if (r.name === metricName) {
          rule = r;
          break;
        }
      }
      if (!rule) {
        continue;
      }

      const value: number = getMapNumber(row, 'value');
      if (value === 0) {
        continue;
      }

      if ((rule.critical_high !== null && value >= rule.critical_high) ||
          (rule.critical_low !== null && value <= rule.critical_low)) {
        critical.push({
          metric_name: metricName,
          value: value,
          unit: rule.unit,
          level: 0,
          message: `${metricName} ${value}${rule.unit} 达到危急值`,
        });
      } else if ((rule.abnormal_high !== null && value >= rule.abnormal_high) ||
                 (rule.abnormal_low !== null && value <= rule.abnormal_low)) {
        abnormal.push({
          metric_name: metricName,
          value: value,
          unit: rule.unit,
          level: 1,
          message: `${metricName} ${value}${rule.unit} 偏高/偏低`,
        });
      }
    }

    const now: Date = new Date();
    for (const taskRow of snapshot.openTasks) {
      const dueDateStr: string = getMapString(taskRow, 'due_date');
      if (dueDateStr.length > 0) {
        const due: Date = new Date(dueDateStr);
        if (due <= now) {
          const titleStr: string = getMapString(taskRow, 'title');
          abnormal.push({
            metric_name: 'task_due',
            value: 0,
            unit: '',
            level: 1,
            message: `待办"${titleStr}"已到期`,
          });
        }
      }
    }
  }

  private async aiInference(
    snapshot: HealthSnapshot,
    abnormalAlerts: RuleAlert[],
    memberId: number,
  ): Promise<PatrolResult> {
    const patrolId: string = `patrol_${Date.now()}_${memberId}`;
    const profileText: string = this.formatSnapshotForAI(snapshot, abnormalAlerts);

    const messages: LLMMsg[] = [
      { role: 'system', content: `你是一个主动健康管家。根据用户的健康画像，判断是否需要主动干预。

输出格式（严格 JSON）：
{"should_push": true/false, "priority": "critical|high|normal|low", "message": "主动消息内容", "tasks": []}

判断原则：
- 危急值 → critical，立即推送
- 异常持续恶化 → high，每周最多1次
- 待办到期 → normal，每天最多1次
- 无异常 → low，不推送
- 消息要口语化、关心式` },
      { role: 'user', content: profileText },
    ];

    try {
      const response = await this.llm.chat(messages, undefined, 0.3, 800);
      const result: AIResultJSON = JSON.parse(response.content) as AIResultJSON;

      const tasks: PatrolTask[] = [];
      if (result.tasks && result.tasks.length > 0) {
        for (const t of result.tasks) {
          tasks.push({
            title: t.title,
            description: t.description,
            category: this.parseTaskCategory(t.category),
            urgency: this.parseTaskUrgency(t.urgency),
            due_date: t.due_date || null,
          });
        }
      }

      return {
        should_push: result.should_push,
        message: result.message || '',
        priority: this.parsePriority(result.priority),
        tasks: tasks,
        patrol_id: patrolId,
      };
    } catch (e) {
      console.error('[PatrolEngine] AI inference failed:', e);
      return {
        should_push: false,
        message: '',
        priority: 'low',
        tasks: [],
        patrol_id: patrolId,
      };
    }
  }

  private async checkFrequency(memberId: number, priority: Priority): Promise<boolean> {
    if (priority === 'critical') {
      return true;
    }
    if (priority === 'low') {
      return false;
    }

    let limit: number = 1;
    let period: string = '-1 days';
    if (priority === 'high') {
      limit = 1;
      period = '-7 days';
    }

    const rs = await this.db.query(
      `SELECT COUNT(*) as count FROM chat_messages WHERE member_id = ? AND source = 'proactive' AND created_at >= datetime('now', ?)`,
      [String(memberId), period]
    );
    const rows: DataRow[] = await this.db.resultSetToArray(rs);
    const count: number = rows.length > 0 ? getMapNumber(rows[0], 'count') : 0;

    return count < limit;
  }

  async saveProactiveMessage(memberId: number, message: string, priority: Priority, patrolId: string): Promise<number> {
    const metadata: string = JSON.stringify({ priority: priority, patrol_id: patrolId });
    const bucket: relationalStore.ValuesBucket = {
      member_id: memberId,
      role: 'assistant',
      content: message,
      source: 'proactive',
      message_type: 'proactive',
      metadata_json: metadata,
    } as relationalStore.ValuesBucket;
    return await this.db.insert('chat_messages', bucket);
  }

  async saveTasks(memberId: number, tasks: PatrolTask[]): Promise<number[]> {
    const taskIds: number[] = [];
    for (const task of tasks) {
      const bucket: relationalStore.ValuesBucket = {
        member_id: memberId,
        title: task.title,
        description: task.description,
        category: task.category,
        urgency: task.urgency,
        due_date: task.due_date,
        status: 'open',
        source: 'proactive',
        auto_generated: 1,
      } as relationalStore.ValuesBucket;
      const id: number = await this.db.insert('health_tasks', bucket);
      taskIds.push(id);
    }
    return taskIds;
  }

  // ============================================================
  // 格式化辅助
  // ============================================================

  private formatCriticalMessage(alerts: RuleAlert[]): string {
    const lines: string[] = [];
    for (const a of alerts) {
      lines.push(`🚨 ${a.message}`);
    }
    return `${lines.join('\n')}\n\n这是危急值，请立即就医。`;
  }

  private formatSnapshotForAI(snapshot: HealthSnapshot, abnormalAlerts: RuleAlert[]): string {
    const parts: string[] = [];

    const name: string = getMapString(snapshot.member, 'name');
    parts.push(`成员：${name.length > 0 ? name : '未知'}`);

    if (snapshot.diagnoses.length > 0) {
      const diagNames: string[] = [];
      for (const d of snapshot.diagnoses) {
        const dn: string = getMapString(d, 'diagnosis_name');
        if (dn.length > 0) {
          diagNames.push(dn);
        }
      }
      parts.push(`诊断：${diagNames.join('、')}`);
    }

    if (snapshot.medications.length > 0) {
      const medNames: string[] = [];
      for (const med of snapshot.medications) {
        const dn: string = getMapString(med, 'drug_name');
        const ds: string = getMapString(med, 'dosage');
        const fr: string = getMapString(med, 'frequency');
        medNames.push(`${dn} ${ds} ${fr}`);
      }
      parts.push(`用药：${medNames.join('；')}`);
    }

    if (snapshot.recentMetrics.length > 0) {
      const metricCount: number = Math.min(10, snapshot.recentMetrics.length);
      const metricStrs: string[] = [];
      for (let i = 0; i < metricCount; i++) {
        const mt: DataRow = snapshot.recentMetrics[i];
        const mn: string = getMapString(mt, 'metric_name');
        const mv: number = getMapNumber(mt, 'value');
        const mu: string = getMapString(mt, 'unit');
        metricStrs.push(`${mn}=${mv}${mu}`);
      }
      parts.push(`近期指标：${metricStrs.join('，')}`);
    }

    if (abnormalAlerts.length > 0) {
      const alertMsgs: string[] = [];
      for (const a of abnormalAlerts) {
        alertMsgs.push(a.message);
      }
      parts.push(`异常项：${alertMsgs.join('；')}`);
    }

    if (snapshot.openTasks.length > 0) {
      const taskNames: string[] = [];
      for (const t of snapshot.openTasks) {
        const tn: string = getMapString(t, 'title');
        if (tn.length > 0) {
          taskNames.push(tn);
        }
      }
      parts.push(`待办：${taskNames.join('、')}`);
    }

    if (snapshot.memorySummary.length > 0) {
      parts.push(`记忆摘要：${snapshot.memorySummary}`);
    }

    return parts.join('\n');
  }

  private generateTasksFromAlerts(alerts: RuleAlert[], urgencyStr: string): PatrolTask[] {
    const tasks: PatrolTask[] = [];
    const tomorrow: string = new Date(Date.now() + 86400000).toISOString().split('T')[0];
    for (const a of alerts) {
      tasks.push({
        title: `${a.metric_name}复查`,
        description: a.message,
        category: 'recheck',
        urgency: this.parseTaskUrgency(urgencyStr),
        due_date: tomorrow,
      });
    }
    return tasks;
  }

  // ============================================================
  // 类型解析辅助
  // ============================================================

  private parsePriority(s: string): Priority {
    if (s === 'critical') return 'critical';
    if (s === 'high') return 'high';
    if (s === 'normal') return 'normal';
    return 'low';
  }

  private parseTaskCategory(s: string): TaskCategory {
    if (s === 'recheck') return 'recheck';
    if (s === 'medication') return 'medication';
    if (s === 'lifestyle') return 'lifestyle';
    if (s === 'visit') return 'visit';
    return 'other';
  }

  private parseTaskUrgency(s: string): TaskUrgency {
    if (s === 'critical') return 'critical';
    if (s === 'urgent') return 'urgent';
    if (s === 'normal') return 'normal';
    return 'low';
  }
}

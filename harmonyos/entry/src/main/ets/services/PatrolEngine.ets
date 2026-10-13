/**
 * 主动健康巡检引擎（ArkTS 版）
 * 
 * 对齐后端 patrol_engine.py 逻辑：
 * 1. 加载成员完整画像
 * 2. 规则层扫描（异常指标、到期待办等）
 * 3. AI 层推理（LLM 综合画像判断是否需要干预）
 * 4. 输出：主动消息（推送）或 静默记录（不推送）
 * 
 * 注意：ArkTS 不支持 Record<K,V>，使用 object 和 Map<K,V> 替代
 */

import { DatabaseService } from './DatabaseService';
import { LLMClient } from './LLMClient';
import { PatrolResult, PatrolTask, Priority } from '../models/HealthModels';

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
// 内部类型
// ============================================================

interface HealthSnapshot {
  member: object;
  recentMetrics: object[];
  abnormalMetrics: object[];
  diagnoses: object[];
  medications: object[];
  openTasks: object[];
  memorySummary: string;
}

interface RuleAlert {
  metric_name: string;
  value: number;
  unit: string;
  level: number; // 0 = critical, 1 = abnormal
  message: string;
}

interface FrequencyLimit {
  critical: number;
  high: number;
  normal: number;
  low: number;
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

  /**
   * 巡检单个成员
   */
  async patrolMember(memberId: number, trigger: string): Promise<PatrolResult> {
    console.info(`[PatrolEngine] Patrolling member ${memberId}, trigger=${trigger}`);

    // 1. 构建画像快照
    const snapshot: HealthSnapshot = await this.buildHealthSnapshot(memberId);

    // 2. 规则层扫描
    const critical: RuleAlert[] = [];
    const abnormal: RuleAlert[] = [];
    this.scanRules(snapshot, critical, abnormal);

    // 3. 如果规则层发现危急值，直接生成紧急消息
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

    // 4. AI 层推理
    const aiResult: PatrolResult = await this.aiInference(snapshot, abnormal, memberId);

    // 5. 频率控制
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

  /**
   * 构建成员健康画像快照
   */
  private async buildHealthSnapshot(memberId: number): Promise<HealthSnapshot> {
    // 基本信息
    const memberRs = await this.db.query(
      `SELECT * FROM family_members WHERE id = ? AND is_deleted = 0`,
      [String(memberId)]
    );
    const memberRows = this.db.resultSetToArray(memberRs);
    const member: object = memberRows.length > 0 ? memberRows[0] : {};

    // 最近指标（最近30天）
    const metricsRs = await this.db.query(
      `SELECT * FROM metric_records WHERE member_id = ? AND measured_at >= datetime('now', '-30 days') ORDER BY measured_at DESC`,
      [String(memberId)]
    );
    const recentMetrics: object[] = this.db.resultSetToArray(metricsRs);

    // 异常指标
    const abnormalRs = await this.db.query(
      `SELECT * FROM metric_records WHERE member_id = ? AND is_abnormal = 1 ORDER BY measured_at DESC LIMIT 10`,
      [String(memberId)]
    );
    const abnormalMetrics: object[] = this.db.resultSetToArray(abnormalRs);

    // 诊断
    const diagRs = await this.db.query(
      `SELECT * FROM diagnoses WHERE member_id = ? ORDER BY created_at DESC`,
      [String(memberId)]
    );
    const diagnoses: object[] = this.db.resultSetToArray(diagRs);

    // 用药
    const medRs = await this.db.query(
      `SELECT * FROM medications WHERE member_id = ? ORDER BY created_at DESC`,
      [String(memberId)]
    );
    const medications: object[] = this.db.resultSetToArray(medRs);

    // 待办任务
    const taskRs = await this.db.query(
      `SELECT * FROM health_tasks WHERE member_id = ? AND status = 'open' ORDER BY due_date ASC`,
      [String(memberId)]
    );
    const openTasks: object[] = this.db.resultSetToArray(taskRs);

    // 长期记忆
    const memberObj = member as Record<string, object>;
    const memorySummary: string = (memberObj['memory_summary'] as string) || '';

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

  /**
   * 规则层扫描
   */
  private scanRules(snapshot: HealthSnapshot, critical: RuleAlert[], abnormal: RuleAlert[]): void {
    for (const metricObj of snapshot.recentMetrics) {
      const metric = metricObj as Record<string, object>;
      const metricName = metric['metric_name'] as string;
      const rule: MetricRule | undefined = CRITICAL_RULES.find((r: MetricRule) => r.name === metricName);
      if (!rule) {
        continue;
      }

      const value = metric['value'] as number;
      if (value === null || value === undefined) {
        continue;
      }

      // 危急值
      if ((rule.critical_high !== null && value >= rule.critical_high) ||
          (rule.critical_low !== null && value <= rule.critical_low)) {
        critical.push({
          metric_name: metricName,
          value: value,
          unit: rule.unit,
          level: 0,
          message: `${metricName} ${value}${rule.unit} 达到危急值`,
        });
      }
      // 异常值
      else if ((rule.abnormal_high !== null && value >= rule.abnormal_high) ||
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

    // 到期待办
    const now: Date = new Date();
    for (const taskObj of snapshot.openTasks) {
      const task = taskObj as Record<string, object>;
      const dueDateStr = task['due_date'] as string;
      if (dueDateStr) {
        const due: Date = new Date(dueDateStr);
        if (due <= now) {
          abnormal.push({
            metric_name: 'task_due',
            value: 0,
            unit: '',
            level: 1,
            message: `待办"${task['title']}"已到期`,
          });
        }
      }
    }
  }

  /**
   * AI 层推理
   */
  private async aiInference(
    snapshot: HealthSnapshot,
    abnormalAlerts: RuleAlert[],
    memberId: number,
  ): Promise<PatrolResult> {
    const patrolId: string = `patrol_${Date.now()}_${memberId}`;
    const profileText: string = this.formatSnapshotForAI(snapshot, abnormalAlerts);

    const messages = [
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
      const result = JSON.parse(response.content) as Record<string, object>;
      const shouldPush = (result['should_push'] as boolean) || false;
      const message = (result['message'] as string) || '';
      const priority = (result['priority'] as Priority) || 'low';
      const tasks = (result['tasks'] as PatrolTask[]) || [];

      return {
        should_push: shouldPush,
        message: message,
        priority: priority,
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

  /**
   * 频率控制
   */
  private async checkFrequency(memberId: number, priority: Priority): Promise<boolean> {
    if (priority === 'critical') {
      return true;
    }
    if (priority === 'low') {
      return false;
    }

    let limit: number = 0;
    let period: string = '';
    if (priority === 'high') {
      limit = 1;
      period = '-7 days';
    } else {
      limit = 1;
      period = '-1 days';
    }

    if (limit === 0) {
      return false;
    }

    const rs = await this.db.query(
      `SELECT COUNT(*) as count FROM chat_messages WHERE member_id = ? AND source = 'proactive' AND created_at >= datetime('now', ?)`,
      [String(memberId), period]
    );
    const rows = this.db.resultSetToArray(rs);
    const countObj = rows[0] as Record<string, object>;
    const count: number = (countObj['count'] as number) || 0;

    return count < limit;
  }

  /**
   * 保存主动消息到数据库
   */
  async saveProactiveMessage(memberId: number, message: string, priority: Priority, patrolId: string): Promise<number> {
    const metadata: string = JSON.stringify({ priority: priority, patrol_id: patrolId });
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
      const id: number = await this.db.insert('health_tasks', {
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
    const lines: string[] = alerts.map((a: RuleAlert) => `🚨 ${a.message}`);
    return `${lines.join('\n')}\n\n这是危急值，请立即就医。`;
  }

  private formatSnapshotForAI(snapshot: HealthSnapshot, abnormalAlerts: RuleAlert[]): string {
    const m = snapshot.member as Record<string, object>;
    const parts: string[] = [];

    parts.push(`成员：${m['name'] || '未知'}`);

    if (snapshot.diagnoses.length > 0) {
      const diagNames: string[] = snapshot.diagnoses.map((d: object) => {
        return (d as Record<string, object>)['diagnosis_name'] as string;
      });
      parts.push(`诊断：${diagNames.join('、')}`);
    }

    if (snapshot.medications.length > 0) {
      const medNames: string[] = snapshot.medications.map((med: object) => {
        const mObj = med as Record<string, object>;
        return `${mObj['drug_name']} ${mObj['dosage']} ${mObj['frequency']}`;
      });
      parts.push(`用药：${medNames.join('；')}`);
    }

    if (snapshot.recentMetrics.length > 0) {
      const metricCount = Math.min(10, snapshot.recentMetrics.length);
      const recent: object[] = snapshot.recentMetrics.slice(0, metricCount);
      const metricStrs: string[] = recent.map((mt: object) => {
        const mObj = mt as Record<string, object>;
        return `${mObj['metric_name']}=${mObj['value']}${mObj['unit']}`;
      });
      parts.push(`近期指标：${metricStrs.join('，')}`);
    }

    if (abnormalAlerts.length > 0) {
      const alertMsgs: string[] = abnormalAlerts.map((a: RuleAlert) => a.message);
      parts.push(`异常项：${alertMsgs.join('；')}`);
    }

    if (snapshot.openTasks.length > 0) {
      const taskNames: string[] = snapshot.openTasks.map((t: object) => {
        return (t as Record<string, object>)['title'] as string;
      });
      parts.push(`待办：${taskNames.join('、')}`);
    }

    if (snapshot.memorySummary) {
      parts.push(`记忆摘要：${snapshot.memorySummary}`);
    }

    return parts.join('\n');
  }

  private generateTasksFromAlerts(alerts: RuleAlert[], urgency: string): PatrolTask[] {
    const tasks: PatrolTask[] = [];
    const tomorrow: string = new Date(Date.now() + 86400000).toISOString().split('T')[0];
    for (const a of alerts) {
      tasks.push({
        title: `${a.metric_name}复查`,
        description: a.message,
        category: 'recheck',
        urgency: urgency,
        due_date: tomorrow,
      });
    }
    return tasks;
  }
}

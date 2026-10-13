/**
 * 咨询服务（ArkTS 版）
 * 
 * ArkTS 核心限制：
 * - 不支持索引签名 → 使用 Map<string, ColumnValue>
 * - 不支持 row['key'] → 使用 row.get('key')
 * - 不支持 object 类型 → 使用具体 interface
 */

import { relationalStore } from '@kit.ArkData';
import { DatabaseService, DataRow, ColumnValue, getMapVal, getMapString, getMapNumber } from './DatabaseService';
import { LLMClient, getHealthTools, ToolDefinition } from './LLMClient';
import { ChatMessage, LLMMessage, LLMToolCall, RiskLevel, Priority } from '../models/HealthModels';

// ============================================================
// 系统提示词 & 风险关键词
// ============================================================

const SYSTEM_PROMPT: string = `你是一个家庭 AI 健康管家，负责管理用户的健康数据和提供健康建议。

你的能力：
1. 记录和查询健康指标（血压、血糖、血脂、心率等）
2. 管理诊断、用药、过敏、家族史等健康信息
3. 提供健康建议和风险评估
4. 提醒复查和就医
5. 解读体检报告

规则：
- 遇到急性症状（胸痛、呼吸困难等）或危急值，必须建议立即就医
- 不要自行开具处方，用药建议仅供参考
- 保持关心、温暖的语气，像一个贴心的家庭医生
- 回答简洁明了，不要长篇大论`;

const S_LEVEL_KEYWORDS: string[] = [
  '开药', '开点', '开个', '开些', '帮我开', '给我开', '配药', '处方',
  '帮我诊断', '给我诊断', '诊断一下', '我该吃什么药', '换个药',
];

const A_LEVEL_KEYWORDS: string[] = [
  '胸痛', '胸闷痛', '呼吸困难', '喘不上气', '急症', '急诊', '窒息',
  '大出血', '昏迷', '抽搐', '剧烈头痛', '相互作用', '副作用', '过敏反应', '中毒',
];

const A_LEVEL_REPLY_KEYWORDS: string[] = [
  '立即就医', '马上就医', '立即就诊', '拨打 120', '拨打120', '呼叫急救', '前往急诊',
];

// ============================================================
// 接口定义
// ============================================================

export interface ChatResult {
  reply: string;
  riskLevel: RiskLevel;
  toolCallNames: string[];
}

interface ToolArgs {
  metric_name?: string;
  info_type?: string;
  value?: number;
  unit?: string;
  context?: string;
  scale_code?: string;
  limit?: number;
}

interface RefRange {
  low: number;
  high: number;
  critLow: number;
  critHigh: number;
}

interface RangeResult {
  isAbnormal: boolean;
  isCritical: boolean;
  refLower: number | null;
  refUpper: number | null;
}

// 工具结果（匿名对象返回用 interface 包装）
interface ToolResultMetrics {
  metrics: DataRow[];
  count: number;
}

interface ToolResultProfile {
  type: string;
  records: DataRow[];
  count: number;
}

interface ToolResultAbnormal {
  abnormal_metrics: DataRow[];
  count: number;
}

interface ToolResultExtract {
  saved: boolean;
  id: number;
  metric_name: string;
  value: number;
  unit: string;
  is_abnormal: boolean;
  is_critical: boolean;
}

interface ToolResultScale {
  scale_code: string;
  scale_name: string;
  message: string;
}

// ============================================================
// 辅助函数
// ============================================================

function parseToolArgs(argsJson: string): ToolArgs {
  try {
    return JSON.parse(argsJson) as ToolArgs;
  } catch (e) {
    return {};
  }
}

function getRefRanges(): Map<string, RefRange> {
  return new Map<string, RefRange>([
    ['blood_pressure_systolic', { low: 90, high: 140, critLow: 90, critHigh: 180 }],
    ['blood_pressure_diastolic', { low: 60, high: 90, critLow: 60, critHigh: 120 }],
    ['glucose_fasting', { low: 3.9, high: 6.1, critLow: 2.8, critHigh: 16.7 }],
    ['glucose_random', { low: 3.9, high: 11.1, critLow: 2.8, critHigh: 16.7 }],
    ['heart_rate', { low: 60, high: 100, critLow: 40, critHigh: 150 }],
  ]);
}

// ============================================================
// 咨询服务
// ============================================================

export class ConsultationService {
  private db: DatabaseService;
  private llm: LLMClient;

  constructor(db: DatabaseService, llm: LLMClient) {
    this.db = db;
    this.llm = llm;
  }

  async chat(memberId: number, userMessage: string, source: string): Promise<ChatResult> {
    const systemPrompt: string = await this.buildSystemPrompt(memberId);
    const history: LLMMessage[] = await this.loadHistory(memberId, 10);
    await this.saveMessage(memberId, 'user', userMessage, source);

    const messages: LLMMessage[] = [{ role: 'system', content: systemPrompt }];
    for (const h of history) {
      messages.push(h);
    }
    messages.push({ role: 'user', content: userMessage });

    const tools: ToolDefinition[] = getHealthTools();
    let response = await this.llm.chat(messages, tools, 0.7, 4096);

    const toolCallNames: string[] = [];
    let maxRounds: number = 5;

    while (response.tool_calls && maxRounds > 0) {
      messages.push({
        role: 'assistant',
        content: response.content,
        tool_calls: response.tool_calls,
      });

      for (const tc of response.tool_calls) {
        toolCallNames.push(tc.function.name);
        const result: string = await this.executeToolCall(tc.function.name, tc.function.arguments, memberId);
        messages.push({
          role: 'tool',
          content: result,
          name: tc.function.name,
          tool_call_id: tc.id,
        });
      }

      response = await this.llm.chat(messages, tools, 0.7, 4096);
      maxRounds--;
    }

    const reply: string = response.content || '';
    const riskLevel: RiskLevel = this.assessRisk(userMessage, reply);
    await this.saveMessage(memberId, 'assistant', reply, source);

    return { reply, riskLevel, toolCallNames };
  }

  async chatStream(
    memberId: number,
    userMessage: string,
    source: string,
    onDelta: (text: string) => void,
    onRisk: (riskLevel: RiskLevel, toolCallNames: string[]) => void,
  ): Promise<void> {
    const systemPrompt: string = await this.buildSystemPrompt(memberId);
    const history: LLMMessage[] = await this.loadHistory(memberId, 10);
    await this.saveMessage(memberId, 'user', userMessage, source);

    const messages: LLMMessage[] = [{ role: 'system', content: systemPrompt }];
    for (const h of history) {
      messages.push(h);
    }
    messages.push({ role: 'user', content: userMessage });

    const tools: ToolDefinition[] = getHealthTools();
    let response = await this.llm.chat(messages, tools, 0.7, 4096);

    const toolCallNames: string[] = [];
    let maxRounds: number = 5;

    while (response.tool_calls && maxRounds > 0) {
      messages.push({
        role: 'assistant',
        content: response.content,
        tool_calls: response.tool_calls,
      });

      for (const tc of response.tool_calls) {
        toolCallNames.push(tc.function.name);
        const result: string = await this.executeToolCall(tc.function.name, tc.function.arguments, memberId);
        messages.push({
          role: 'tool',
          content: result,
          name: tc.function.name,
          tool_call_id: tc.id,
        });
      }

      response = await this.llm.chat(messages, tools, 0.7, 4096);
      maxRounds--;
    }

    const reply: string = response.content || '';
    const chunkSize: number = 20;
    for (let i = 0; i < reply.length; i += chunkSize) {
      const end: number = Math.min(i + chunkSize, reply.length);
      onDelta(reply.substring(i, end));
    }

    const riskLevel: RiskLevel = this.assessRisk(userMessage, reply);
    onRisk(riskLevel, toolCallNames);
    await this.saveMessage(memberId, 'assistant', reply, source);
  }

  // ============================================================
  // 内部方法
  // ============================================================

  private async buildSystemPrompt(memberId: number): Promise<string> {
    let prompt: string = SYSTEM_PROMPT;
    try {
      const rs = await this.db.query(
        `SELECT memory_summary FROM family_members WHERE id = ?`,
        [String(memberId)]
      );
      const rows: DataRow[] = await this.db.resultSetToArray(rs);
      if (rows.length > 0) {
        const summary: string = getMapString(rows[0], 'memory_summary');
        if (summary.length > 0) {
          prompt += `\n\n[长期记忆]\n${summary}`;
        }
      }
    } catch (e) {
      // ignore
    }
    return prompt;
  }

  private async loadHistory(memberId: number, limit: number): Promise<LLMMessage[]> {
    const rs = await this.db.query(
      `SELECT role, content FROM chat_messages 
       WHERE member_id = ? AND source IN ('webui', 'proactive') 
       ORDER BY id DESC LIMIT ?`,
      [String(memberId), String(limit)]
    );
    const rows: DataRow[] = await this.db.resultSetToArray(rs);
    const result: LLMMessage[] = [];
    for (let i = rows.length - 1; i >= 0; i--) {
      result.push({
        role: getMapString(rows[i], 'role'),
        content: getMapString(rows[i], 'content'),
      });
    }
    return result;
  }

  private async saveMessage(
    memberId: number,
    role: string,
    content: string,
    source: string,
  ): Promise<void> {
    const bucket: relationalStore.ValuesBucket = {
      member_id: memberId,
      role: role,
      content: content,
      source: source,
      message_type: 'normal',
    } as relationalStore.ValuesBucket;
    await this.db.insert('chat_messages', bucket);
  }

  private assessRisk(userMessage: string, reply: string): RiskLevel {
    const user: string = (userMessage || '').toLowerCase();
    for (const kw of S_LEVEL_KEYWORDS) {
      if (user.includes(kw)) {
        return 'S';
      }
    }
    for (const kw of A_LEVEL_KEYWORDS) {
      if (user.includes(kw)) {
        return 'A';
      }
    }
    const assistantReply: string = (reply || '').toLowerCase();
    for (const kw of A_LEVEL_REPLY_KEYWORDS) {
      if (assistantReply.includes(kw)) {
        return 'A';
      }
    }
    return 'B';
  }

  private async executeToolCall(
    name: string,
    argsJson: string,
    memberId: number,
  ): Promise<string> {
    try {
      const args: ToolArgs = parseToolArgs(argsJson);

      if (name === 'query_metrics') {
        const result: ToolResultMetrics = await this.toolQueryMetrics(memberId, args);
        return JSON.stringify(result);
      }
      if (name === 'query_profile') {
        const result: ToolResultProfile = await this.toolQueryProfile(memberId, args);
        return JSON.stringify(result);
      }
      if (name === 'query_abnormal') {
        const result: ToolResultAbnormal = await this.toolQueryAbnormal(memberId);
        return JSON.stringify(result);
      }
      if (name === 'extract_and_save') {
        const result: ToolResultExtract = await this.toolExtractAndSave(memberId, args);
        return JSON.stringify(result);
      }
      if (name === 'assess_scale') {
        const result: ToolResultScale = await this.toolAssessScale(args);
        return JSON.stringify(result);
      }
      return JSON.stringify({ error: `Unknown tool: ${name}` });
    } catch (e) {
      return JSON.stringify({ error: `Tool execution failed: ${e}` });
    }
  }

  private async toolQueryMetrics(memberId: number, args: ToolArgs): Promise<ToolResultMetrics> {
    const metricName: string = args.metric_name || '';
    const limit: number = args.limit || 10;
    let sql: string = `SELECT * FROM metric_records WHERE member_id = ?`;
    const sqlArgs: string[] = [String(memberId)];
    if (metricName.length > 0) {
      sql += ` AND metric_name = ?`;
      sqlArgs.push(metricName);
    }
    sql += ` ORDER BY measured_at DESC LIMIT ?`;
    sqlArgs.push(String(limit));

    const rs = await this.db.query(sql, sqlArgs);
    const rows: DataRow[] = await this.db.resultSetToArray(rs);
    return { metrics: rows, count: rows.length };
  }

  private async toolQueryProfile(memberId: number, args: ToolArgs): Promise<ToolResultProfile> {
    const infoType: string = args.info_type || 'diagnoses';
    const allowed: string[] = ['diagnoses', 'medications', 'allergies', 'family_histories', 'surgeries', 'vaccinations'];
    if (allowed.indexOf(infoType) < 0) {
      return { type: infoType, records: [], count: 0 };
    }
    const rs = await this.db.query(
      `SELECT * FROM ${infoType} WHERE member_id = ? ORDER BY created_at DESC`,
      [String(memberId)]
    );
    const rows: DataRow[] = await this.db.resultSetToArray(rs);
    return { type: infoType, records: rows, count: rows.length };
  }

  private async toolQueryAbnormal(memberId: number): Promise<ToolResultAbnormal> {
    const rs = await this.db.query(
      `SELECT * FROM metric_records WHERE member_id = ? AND is_abnormal = 1 ORDER BY measured_at DESC LIMIT 10`,
      [String(memberId)]
    );
    const rows: DataRow[] = await this.db.resultSetToArray(rs);
    return { abnormal_metrics: rows, count: rows.length };
  }

  private async toolExtractAndSave(memberId: number, args: ToolArgs): Promise<ToolResultExtract> {
    const metricName: string = args.metric_name || '';
    const value: number = args.value || 0;
    const unit: string = args.unit || '';
    const context: string = args.context || '';

    const rangeResult: RangeResult = this.checkReferenceRange(metricName, value);

    const bucket: relationalStore.ValuesBucket = {
      member_id: memberId,
      metric_name: metricName,
      value: value,
      unit: unit,
      reference_lower: rangeResult.refLower,
      reference_upper: rangeResult.refUpper,
      is_abnormal: rangeResult.isAbnormal ? 1 : 0,
      is_critical: rangeResult.isCritical ? 1 : 0,
      measured_at: new Date().toISOString(),
      context: context.length > 0 ? context : null,
      source_type: 'chat_extract',
    } as relationalStore.ValuesBucket;

    const id: number = await this.db.insert('metric_records', bucket);

    return {
      saved: true,
      id: id,
      metric_name: metricName,
      value: value,
      unit: unit,
      is_abnormal: rangeResult.isAbnormal,
      is_critical: rangeResult.isCritical,
    };
  }

  private async toolAssessScale(args: ToolArgs): Promise<ToolResultScale> {
    const scaleCode: string = args.scale_code || '';
    const scaleNames: Map<string, string> = new Map<string, string>([
      ['phq9', 'PHQ-9 抑郁症筛查量表'],
      ['gad7', 'GAD-7 焦虑症筛查量表'],
      ['diabetes', '糖尿病风险评分'],
      ['ascvd', 'ASCVD 心血管疾病风险评估'],
      ['isi', 'ISI 失眠严重程度指数'],
      ['hypertension', '高血压风险评分'],
      ['lipid', '血脂异常评估'],
      ['ad8', 'AD8 认知功能筛查'],
      ['stroke', '卒中风险评分'],
    ]);
    const scaleName: string = scaleNames.get(scaleCode) || scaleCode;
    return {
      scale_code: scaleCode,
      scale_name: scaleName,
      message: `请在量表页面完成${scaleName}评估`,
    };
  }

  private checkReferenceRange(metricName: string, value: number): RangeResult {
    const ranges: Map<string, RefRange> = getRefRanges();
    const range: RefRange | undefined = ranges.get(metricName);
    if (!range) {
      return { isAbnormal: false, isCritical: false, refLower: null, refUpper: null };
    }
    const isCritical: boolean = value <= range.critLow || value >= range.critHigh;
    const isAbnormal: boolean = value < range.low || value > range.high;
    return { isAbnormal, isCritical, refLower: range.low, refUpper: range.high };
  }
}

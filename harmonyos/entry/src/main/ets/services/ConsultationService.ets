/**
 * 咨询服务（ArkTS 版）
 * 
 * 对齐后端 consultation.py 逻辑：
 * 1. 构建 system prompt（含画像信息）
 * 2. 加载对话历史
 * 3. 调用 LLM（带工具调用）
 * 4. 执行工具调用
 * 5. 风险评估
 * 6. 保存消息
 * 
 * 注意：ArkTS 不支持 async generator，流式输出使用回调
 */

import { DatabaseService } from './DatabaseService';
import { LLMClient, getHealthTools, ToolDefinition } from './LLMClient';
import { ChatMessage, LLMMessage, RiskLevel } from '../models/HealthModels';

// ============================================================
// 系统提示词
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

// ============================================================
// 风险评估关键词
// ============================================================

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
// 查询结果接口
// ============================================================

export interface ChatResult {
  reply: string;
  riskLevel: RiskLevel;
  toolCallNames: string[];
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

  /**
   * 非流式对话
   */
  async chat(memberId: number, userMessage: string, source: string): Promise<ChatResult> {
    // 1. 构建消息
    const systemPrompt: string = await this.buildSystemPrompt(memberId);
    const history: LLMMessage[] = await this.loadHistory(memberId, 10);
    await this.saveMessage(memberId, 'user', userMessage, source);

    const messages: LLMMessage[] = [ { role: 'system', content: systemPrompt } ];
    for (const h of history) {
      messages.push(h);
    }
    messages.push({ role: 'user', content: userMessage });

    // 2. 调用 LLM（带工具）
    const tools: ToolDefinition[] = getHealthTools();
    let response = await this.llm.chat(messages, tools, 0.7, 4096);

    // 3. 处理工具调用
    const toolCallNames: string[] = [];
    let maxRounds: number = 5;

    while (response.tool_calls && maxRounds > 0) {
      // 添加 assistant 消息
      const assistantMsg: LLMMessage = {
        role: 'assistant',
        content: response.content,
        tool_calls: response.tool_calls.map(tc => ({
          id: tc.id,
          type: 'function',
          function: { name: tc.name, arguments: tc.arguments },
        })),
      };
      messages.push(assistantMsg);

      // 执行工具调用
      for (const tc of response.tool_calls) {
        toolCallNames.push(tc.name);
        const result: string = await this.executeToolCall(tc.name, tc.arguments, memberId);
        const toolMsg: LLMMessage = {
          role: 'tool',
          content: result,
          name: tc.name,
          tool_call_id: tc.id,
        };
        messages.push(toolMsg);
      }

      response = await this.llm.chat(messages, tools, 0.7, 4096);
      maxRounds--;
    }

    const reply: string = response.content || '';

    // 4. 风险评估
    const riskLevel: RiskLevel = this.assessRisk(userMessage, reply);

    // 5. 保存回复
    await this.saveMessage(memberId, 'assistant', reply, source);

    return { reply, riskLevel, toolCallNames };
  }

  /**
   * 流式对话（回调模式）
   * @param onDelta 每段文本回调
   * @param onRisk 风险评估回调
   */
  async chatStream(
    memberId: number,
    userMessage: string,
    source: string,
    onDelta: (text: string) => void,
    onRisk: (riskLevel: RiskLevel, toolCallNames: string[]) => void,
  ): Promise<void> {
    // 1. 构建消息
    const systemPrompt: string = await this.buildSystemPrompt(memberId);
    const history: LLMMessage[] = await this.loadHistory(memberId, 10);
    await this.saveMessage(memberId, 'user', userMessage, source);

    const messages: LLMMessage[] = [ { role: 'system', content: systemPrompt } ];
    for (const h of history) {
      messages.push(h);
    }
    messages.push({ role: 'user', content: userMessage });

    // 2. 非流式调用（带工具）处理工具调用
    const tools: ToolDefinition[] = getHealthTools();
    let response = await this.llm.chat(messages, tools, 0.7, 4096);

    // 3. 处理工具调用循环
    const toolCallNames: string[] = [];
    let maxRounds: number = 5;

    while (response.tool_calls && maxRounds > 0) {
      const assistantMsg: LLMMessage = {
        role: 'assistant',
        content: response.content,
        tool_calls: response.tool_calls.map(tc => ({
          id: tc.id,
          type: 'function',
          function: { name: tc.name, arguments: tc.arguments },
        })),
      };
      messages.push(assistantMsg);

      for (const tc of response.tool_calls) {
        toolCallNames.push(tc.name);
        const result: string = await this.executeToolCall(tc.name, tc.arguments, memberId);
        messages.push({
          role: 'tool',
          content: result,
          name: tc.name,
          tool_call_id: tc.id,
        });
      }

      response = await this.llm.chat(messages, tools, 0.7, 4096);
      maxRounds--;
    }

    // 4. 模拟流式输出（分块回调）
    const reply: string = response.content || '';
    const chunkSize: number = 20;
    for (let i = 0; i < reply.length; i += chunkSize) {
      const end: number = Math.min(i + chunkSize, reply.length);
      onDelta(reply.substring(i, end));
    }

    // 5. 风险评估
    const riskLevel: RiskLevel = this.assessRisk(userMessage, reply);
    onRisk(riskLevel, toolCallNames);

    // 6. 保存回复
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
      const rows = this.db.resultSetToArray(rs);
      if (rows.length > 0) {
        const summary = rows[0]['memory_summary'] as string;
        if (summary) {
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
    const rows = this.db.resultSetToArray(rs);
    // 反转为时间顺序
    const result: LLMMessage[] = [];
    for (let i = rows.length - 1; i >= 0; i--) {
      result.push({
        role: rows[i]['role'] as string,
        content: rows[i]['content'] as string,
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
    await this.db.insert('chat_messages', {
      member_id: memberId,
      role: role,
      content: content,
      source: source,
      message_type: 'normal',
    });
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

  /**
   * 执行工具调用，返回 JSON 字符串结果
   */
  private async executeToolCall(
    name: string,
    args: string,
    memberId: number,
  ): Promise<string> {
    try {
      const params = JSON.parse(args) as Map<string, object>;
      let result: object;

      switch (name) {
        case 'query_metrics':
          result = await this.toolQueryMetrics(memberId, params);
          break;
        case 'query_profile':
          result = await this.toolQueryProfile(memberId, params);
          break;
        case 'query_abnormal':
          result = await this.toolQueryAbnormal(memberId);
          break;
        case 'extract_and_save':
          result = await this.toolExtractAndSave(memberId, params);
          break;
        case 'assess_scale':
          result = await this.toolAssessScale(memberId, params);
          break;
        default:
          result = { error: `Unknown tool: ${name}` };
      }
      return JSON.stringify(result);
    } catch (e) {
      return JSON.stringify({ error: `Tool execution failed: ${e}` });
    }
  }

  private async toolQueryMetrics(memberId: number, params: Map<string, object>): Promise<object> {
    const metricName = params.get('metric_name') as string;
    const limit = (params.get('limit') as number) || 10;
    let sql = `SELECT * FROM metric_records WHERE member_id = ?`;
    const sqlArgs: string[] = [String(memberId)];
    if (metricName) {
      sql += ` AND metric_name = ?`;
      sqlArgs.push(metricName);
    }
    sql += ` ORDER BY measured_at DESC LIMIT ?`;
    sqlArgs.push(String(limit));

    const rs = await this.db.query(sql, sqlArgs);
    const rows = this.db.resultSetToArray(rs);
    return { metrics: rows, count: rows.length };
  }

  private async toolQueryProfile(memberId: number, params: Map<string, object>): Promise<object> {
    const infoType = (params.get('info_type') as string) || 'diagnoses';
    const allowed: string[] = ['diagnoses', 'medications', 'allergies', 'family_histories', 'surgeries', 'vaccinations'];
    if (allowed.indexOf(infoType) < 0) {
      return { error: `Invalid info_type: ${infoType}` };
    }
    const rs = await this.db.query(
      `SELECT * FROM ${infoType} WHERE member_id = ? ORDER BY created_at DESC`,
      [String(memberId)]
    );
    const rows = this.db.resultSetToArray(rs);
    return { type: infoType, records: rows, count: rows.length };
  }

  private async toolQueryAbnormal(memberId: number): Promise<object> {
    const rs = await this.db.query(
      `SELECT * FROM metric_records WHERE member_id = ? AND is_abnormal = 1 ORDER BY measured_at DESC LIMIT 10`,
      [String(memberId)]
    );
    const rows = this.db.resultSetToArray(rs);
    return { abnormal_metrics: rows, count: rows.length };
  }

  private async toolExtractAndSave(memberId: number, params: Map<string, object>): Promise<object> {
    const metricName = params.get('metric_name') as string;
    const value = params.get('value') as number;
    const unit = (params.get('unit') as string) || '';
    const context = (params.get('context') as string) || null;

    const rangeResult = this.checkReferenceRange(metricName, value);

    const id = await this.db.insert('metric_records', {
      member_id: memberId,
      metric_name: metricName,
      value: value,
      unit: unit,
      reference_lower: rangeResult.refLower,
      reference_upper: rangeResult.refUpper,
      is_abnormal: rangeResult.isAbnormal ? 1 : 0,
      is_critical: rangeResult.isCritical ? 1 : 0,
      measured_at: new Date().toISOString(),
      context: context,
      source_type: 'chat_extract',
    });

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

  private async toolAssessScale(memberId: number, params: Map<string, object>): Promise<object> {
    const scaleCode = params.get('scale_code') as string;
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
    const scaleName = scaleNames.get(scaleCode) || scaleCode;
    return {
      scale_code: scaleCode,
      scale_name: scaleName,
      message: `请在量表页面完成${scaleName}评估`,
    };
  }

  /**
   * 简化的参考范围检查
   */
  private checkReferenceRange(metricName: string, value: number): {
    isAbnormal: boolean; isCritical: boolean; refLower: number | null; refUpper: number | null;
  } {
    interface Range {
      low: number; high: number; critLow: number; critHigh: number;
    }
    const ranges: Map<string, Range> = new Map<string, Range>([
      ['blood_pressure_systolic', { low: 90, high: 140, critLow: 90, critHigh: 180 }],
      ['blood_pressure_diastolic', { low: 60, high: 90, critLow: 60, critHigh: 120 }],
      ['glucose_fasting', { low: 3.9, high: 6.1, critLow: 2.8, critHigh: 16.7 }],
      ['glucose_random', { low: 3.9, high: 11.1, critLow: 2.8, critHigh: 16.7 }],
      ['heart_rate', { low: 60, high: 100, critLow: 40, critHigh: 150 }],
    ]);

    const range = ranges.get(metricName);
    if (!range) {
      return { isAbnormal: false, isCritical: false, refLower: null, refUpper: null };
    }

    const isCritical: boolean = value <= range.critLow || value >= range.critHigh;
    const isAbnormal: boolean = value < range.low || value > range.high;
    return { isAbnormal, isCritical, refLower: range.low, refUpper: range.high };
  }
}

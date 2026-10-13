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
 */

import { DatabaseService } from './DatabaseService';
import { LLMClient, HEALTH_TOOLS, ToolDefinition } from './LLMClient';
import { ChatMessage, LLMMessage, RiskLevel } from '../models/HealthModels';

// ============================================================
// 系统提示词（对齐后端 system prompt）
// ============================================================

const SYSTEM_PROMPT = `你是一个家庭 AI 健康管家，负责管理用户的健康数据和提供健康建议。

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
- 回答简洁明了，不要长篇大论

当前可用工具：
- query_metrics: 查询健康指标
- query_profile: 查询诊断/用药记录
- query_abnormal: 查询异常指标
- extract_and_save: 提取并保存健康数据
- assess_scale: 调用量表评估`;

// ============================================================
// 风险评估关键词
// ============================================================

const S_LEVEL_KEYWORDS = [
  '开药', '开点', '开个', '开些', '帮我开', '给我开', '配药', '处方',
  '帮我诊断', '给我诊断', '诊断一下', '我该吃什么药', '换个药',
];

const A_LEVEL_KEYWORDS = [
  '胸痛', '胸闷痛', '呼吸困难', '喘不上气', '急症', '急诊', '窒息',
  '大出血', '昏迷', '抽搐', '剧烈头痛', '相互作用', '副作用', '过敏反应', '中毒',
];

const A_LEVEL_REPLY_KEYWORDS = [
  '立即就医', '马上就医', '立即就诊', '拨打 120', '拨打120', '呼叫急救', '前往急诊',
];

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
  async chat(
    memberId: number,
    userMessage: string,
    source: string = 'webui',
  ): Promise<{ reply: string; riskLevel: RiskLevel; toolCalls: object[] }> {
    // 1. 构建消息
    const systemPrompt = await this.buildSystemPrompt(memberId);
    const history = await this.loadHistory(memberId, 10);
    await this.saveMessage(memberId, 'user', userMessage, source);

    const messages: LLMMessage[] = [
      { role: 'system', content: systemPrompt },
      ...history,
      { role: 'user', content: userMessage },
    ];

    // 2. 调用 LLM（带工具）
    let response = await this.llm.chat(messages, HEALTH_TOOLS, 0.7, 4096);

    // 3. 处理工具调用
    const toolCallRecords: object[] = [];
    let maxRounds = 5;

    while (response.tool_calls && maxRounds > 0) {
      // 添加 assistant 消息（含 tool_calls）
      messages.push({
        role: 'assistant',
        content: response.content,
        tool_calls: response.tool_calls.map(tc => ({
          id: tc.id,
          type: 'function',
          function: { name: tc.name, arguments: tc.arguments },
        })),
      });

      // 执行工具调用
      for (const tc of response.tool_calls) {
        const result = await this.executeToolCall(tc.name, tc.arguments, memberId);
        toolCallRecords.push({ name: tc.name, arguments: tc.arguments, result });
        messages.push({
          role: 'tool',
          content: JSON.stringify(result),
          name: tc.name,
          tool_call_id: tc.id,
        });
      }

      // 下一轮
      response = await this.llm.chat(messages, HEALTH_TOOLS, 0.7, 4096);
      maxRounds--;
    }

    // 4. 检测原始 tool-call 标记
    const reply = response.content || '';

    // 5. 风险评估
    const riskLevel = this.assessRisk(userMessage, reply);

    // 6. 保存回复
    await this.saveMessage(memberId, 'assistant', reply, source);

    return { reply, riskLevel, toolCalls: toolCallRecords };
  }

  /**
   * 流式对话
   * @returns AsyncGenerator，逐字 yield
   */
  async *chatStream(
    memberId: number,
    userMessage: string,
    source: string = 'webui',
  ): AsyncGenerator<{ type: string; data: string }> {
    // 1. 构建消息
    const systemPrompt = await this.buildSystemPrompt(memberId);
    const history = await this.loadHistory(memberId, 10);
    await this.saveMessage(memberId, 'user', userMessage, source);

    const messages: LLMMessage[] = [
      { role: 'system', content: systemPrompt },
      ...history,
      { role: 'user', content: userMessage },
    ];

    // 2. 非流式调用（带工具）
    let response = await this.llm.chat(messages, HEALTH_TOOLS, 0.7, 4096);

    // 3. 处理工具调用
    const toolCallRecords: object[] = [];
    let maxRounds = 5;

    while (response.tool_calls && maxRounds > 0) {
      messages.push({
        role: 'assistant',
        content: response.content,
        tool_calls: response.tool_calls.map(tc => ({
          id: tc.id,
          type: 'function',
          function: { name: tc.name, arguments: tc.arguments },
        })),
      });

      for (const tc of response.tool_calls) {
        const result = await this.executeToolCall(tc.name, tc.arguments, memberId);
        toolCallRecords.push({ name: tc.name, arguments: tc.arguments, result });
        messages.push({
          role: 'tool',
          content: JSON.stringify(result),
          name: tc.name,
          tool_call_id: tc.id,
        });
      }

      response = await this.llm.chat(messages, HEALTH_TOOLS, 0.7, 4096);
      maxRounds--;
    }

    // 4. 如果有内容，分块模拟流式输出
    const reply = response.content || '';
    const chunkSize = 20;
    for (let i = 0; i < reply.length; i += chunkSize) {
      yield { type: 'delta', data: reply.slice(i, i + chunkSize) };
      // 小延迟让前端渲染
      await new Promise(resolve => setTimeout(resolve, 20));
    }

    // 5. 风险评估
    const riskLevel = this.assessRisk(userMessage, reply);
    yield {
      type: 'risk',
      data: JSON.stringify({ risk_level: riskLevel, tool_calls: toolCallRecords }),
    };

    // 6. 保存回复
    await this.saveMessage(memberId, 'assistant', reply, source);
  }

  // ============================================================
  // 内部方法
  // ============================================================

  private async buildSystemPrompt(memberId: number): Promise<string> {
    let prompt = SYSTEM_PROMPT;

    // 注入长期记忆
    try {
      const rs = await this.db.query(
        `SELECT memory_summary FROM family_members WHERE id = ?`,
        [String(memberId)]
      );
      const rows = this.db.resultSetToArray(rs);
      if (rows.length > 0 && rows[0]['memory_summary']) {
        prompt += `\n\n[长期记忆]\n${rows[0]['memory_summary']}`;
      }
    } catch {
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
    return rows.reverse().map(row => ({
      role: row['role'] as string,
      content: row['content'] as string,
    }));
  }

  private async saveMessage(
    memberId: number,
    role: string,
    content: string,
    source: string,
  ): Promise<void> {
    await this.db.insert('chat_messages', {
      member_id: memberId,
      role,
      content,
      source,
      message_type: 'normal',
    });
  }

  private assessRisk(userMessage: string, reply: string): RiskLevel {
    const user = (userMessage || '').toLowerCase();
    if (S_LEVEL_KEYWORDS.some(kw => user.includes(kw))) return 'S';
    if (A_LEVEL_KEYWORDS.some(kw => user.includes(kw))) return 'A';

    const assistantReply = (reply || '').toLowerCase();
    if (A_LEVEL_REPLY_KEYWORDS.some(kw => assistantReply.includes(kw))) return 'A';

    return 'B';
  }

  /**
   * 执行工具调用
   */
  private async executeToolCall(
    name: string,
    args: string,
    memberId: number,
  ): Promise<Record<string, object>> {
    try {
      const params = JSON.parse(args);
      
      switch (name) {
        case 'query_metrics':
          return await this.toolQueryMetrics(memberId, params);
        case 'query_profile':
          return await this.toolQueryProfile(memberId, params);
        case 'query_abnormal':
          return await this.toolQueryAbnormal(memberId);
        case 'extract_and_save':
          return await this.toolExtractAndSave(memberId, params);
        case 'assess_scale':
          return await this.toolAssessScale(memberId, params);
        default:
          return { error: `Unknown tool: ${name}` };
      }
    } catch (e) {
      return { error: `Tool execution failed: ${e}` };
    }
  }

  private async toolQueryMetrics(memberId: number, params: Record<string, object>): Promise<Record<string, object>> {
    const metricName = params['metric_name'] as string;
    const limit = (params['limit'] as number) || 10;
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

  private async toolQueryProfile(memberId: number, params: Record<string, object>): Promise<Record<string, object>> {
    const infoType = (params['info_type'] as string) || 'diagnoses';
    const allowed = ['diagnoses', 'medications', 'allergies', 'family_histories', 'surgeries', 'vaccinations'];
    if (!allowed.includes(infoType)) {
      return { error: `Invalid info_type: ${infoType}` };
    }
    const rs = await this.db.query(
      `SELECT * FROM ${infoType} WHERE member_id = ? ORDER BY created_at DESC`,
      [String(memberId)]
    );
    const rows = this.db.resultSetToArray(rs);
    return { type: infoType, records: rows, count: rows.length };
  }

  private async toolQueryAbnormal(memberId: number): Promise<Record<string, object>> {
    const rs = await this.db.query(
      `SELECT * FROM metric_records WHERE member_id = ? AND is_abnormal = 1 ORDER BY measured_at DESC LIMIT 10`,
      [String(memberId)]
    );
    const rows = this.db.resultSetToArray(rs);
    return { abnormal_metrics: rows, count: rows.length };
  }

  private async toolExtractAndSave(memberId: number, params: Record<string, object>): Promise<Record<string, object>> {
    const metricName = params['metric_name'] as string;
    const value = params['value'] as number;
    const unit = (params['unit'] as string) || '';
    const context = params['context'] as string || null;

    // 简化的参考范围检查
    const { isAbnormal, isCritical, refLower, refUpper } = this.checkReferenceRange(metricName, value);

    const id = await this.db.insert('metric_records', {
      member_id: memberId,
      metric_name: metricName,
      value,
      unit,
      reference_lower: refLower,
      reference_upper: refUpper,
      is_abnormal: isAbnormal ? 1 : 0,
      is_critical: isCritical ? 1 : 0,
      measured_at: new Date().toISOString(),
      context,
      source_type: 'chat_extract',
    });

    return { saved: true, id, metric_name: metricName, value, unit, is_abnormal: isAbnormal, is_critical: isCritical };
  }

  private async toolAssessScale(memberId: number, params: Record<string, object>): Promise<Record<string, object>> {
    const scaleCode = params['scale_code'] as string;
    // MVP：返回量表信息，前端展示量表
    const scaleInfo: Record<string, string> = {
      phq9: 'PHQ-9 抑郁症筛查量表',
      gad7: 'GAD-7 焦虑症筛查量表',
      diabetes: '糖尿病风险评分',
      ascvd: 'ASCVD 心血管疾病风险评估',
      isi: 'ISI 失眠严重程度指数',
      hypertension: '高血压风险评分',
      lipid: '血脂异常评估',
      ad8: 'AD8 认知功能筛查',
      stroke: '卒中风险评分',
    };
    return {
      scale_code: scaleCode,
      scale_name: scaleInfo[scaleCode] || scaleCode,
      message: `请在量表页面完成${scaleInfo[scaleCode] || scaleCode}评估`,
    };
  }

  /**
   * 简化的参考范围检查
   */
  private checkReferenceRange(metricName: string, value: number): {
    isAbnormal: boolean; isCritical: boolean; refLower: number | null; refUpper: number | null;
  } {
    const ranges: Record<string, { low: number; high: number; critLow: number; critHigh: number }> = {
      blood_pressure_systolic: { low: 90, high: 140, critLow: 90, critHigh: 180 },
      blood_pressure_diastolic: { low: 60, high: 90, critLow: 60, critHigh: 120 },
      glucose_fasting: { low: 3.9, high: 6.1, critLow: 2.8, critHigh: 16.7 },
      glucose_random: { low: 3.9, high: 11.1, critLow: 2.8, critHigh: 16.7 },
      heart_rate: { low: 60, high: 100, critLow: 40, critHigh: 150 },
    };

    const range = ranges[metricName];
    if (!range) {
      return { isAbnormal: false, isCritical: false, refLower: null, refUpper: null };
    }

    const isCritical = value <= range.critLow || value >= range.critHigh;
    const isAbnormal = value < range.low || value > range.high;
    return { isAbnormal, isCritical, refLower: range.low, refUpper: range.high };
  }
}

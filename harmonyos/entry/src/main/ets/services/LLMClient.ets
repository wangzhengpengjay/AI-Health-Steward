/**
 * LLM 客户端服务
 * 
 * 通过 HTTP 调用云端 LLM API（OpenAI 兼容格式）
 * 支持：对话、流式输出、工具调用
 */

import http from '@ohos.net.http';
import { LLMMessage, LLMResponse, LLMToolCall } from '../models/HealthModels';

// ============================================================
// 配置
// ============================================================

export interface LLMConfig {
  baseUrl: string;
  apiKey: string;
  model: string;
  temperature: number;
  maxTokens: number;
}

// ============================================================
// 工具定义（对齐后端 tool registry）
// ============================================================

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: Record<string, object>;
}

export const HEALTH_TOOLS: ToolDefinition[] = [
  {
    name: 'query_metrics',
    description: '查询家庭成员的健康指标记录（如血压、血糖、血脂等）',
    parameters: {
      type: 'object',
      properties: {
        metric_name: { type: 'string', description: '指标名称，如 blood_pressure_systolic, glucose, total_cholesterol 等' },
        limit: { type: 'integer', description: '返回最近N条记录，默认10' },
      },
    },
  },
  {
    name: 'query_profile',
    description: '查询家庭成员的诊断、用药、过敏、家族史等基本健康信息',
    parameters: {
      type: 'object',
      properties: {
        info_type: { type: 'string', description: '查询类型：diagnoses, medications, allergies, family_history, surgeries, vaccinations' },
      },
    },
  },
  {
    name: 'query_abnormal',
    description: '查询家庭成员的异常指标记录',
    parameters: {
      type: 'object',
      properties: {},
    },
  },
  {
    name: 'extract_and_save',
    description: '从用户消息中提取健康数据并保存（如血压、血糖等指标）',
    parameters: {
      type: 'object',
      properties: {
        metric_name: { type: 'string', description: '指标名称' },
        value: { type: 'number', description: '数值' },
        unit: { type: 'string', description: '单位' },
        measured_at: { type: 'string', description: '测量时间，ISO格式' },
        context: { type: 'string', description: '上下文，如 空腹/餐后' },
      },
      required: ['metric_name', 'value'],
    },
  },
  {
    name: 'assess_scale',
    description: '调用健康量表评估（如 PHQ-9 抑郁、GAD-7 焦虑、糖尿病风险等）',
    parameters: {
      type: 'object',
      properties: {
        scale_code: { type: 'string', description: '量表代码：phq9, gad7, diabetes, ascvd, isi, hypertension, lipid, ad8, stroke' },
      },
      required: ['scale_code'],
    },
  },
];

// ============================================================
// LLM 客户端
// ============================================================

export class LLMClient {
  private config: LLMConfig;

  constructor(config: LLMConfig) {
    this.config = config;
  }

  /**
   * 非流式对话
   */
  async chat(
    messages: LLMMessage[],
    tools?: ToolDefinition[],
    temperature?: number,
    maxTokens?: number,
  ): Promise<LLMResponse> {
    const payload: Record<string, object> = {
      model: this.config.model,
      messages: messages.map(m => {
        const msg: Record<string, object> = { role: m.role, content: m.content };
        if (m.tool_calls) msg['tool_calls'] = m.tool_calls;
        if (m.tool_call_id) msg['tool_call_id'] = m.tool_call_id;
        if (m.name) msg['name'] = m.name;
        return msg;
      }),
      temperature: temperature ?? this.config.temperature,
      max_tokens: maxTokens ?? this.config.maxTokens,
    };

    if (tools && tools.length > 0) {
      payload['tools'] = tools.map(t => ({
        type: 'function',
        function: {
          name: t.name,
          description: t.description,
          parameters: t.parameters,
        },
      }));
    }

    const httpRequest = http.createHttp();
    try {
      const response = await httpRequest.request(`${this.config.baseUrl}/chat/completions`, {
        method: http.RequestMethod.POST,
        header: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.config.apiKey}`,
        },
        extraData: JSON.stringify(payload),
        connectTimeout: 30000,
        readTimeout: 120000,
      });

      if (response.responseCode !== 200) {
        throw new Error(`LLM API error: ${response.responseCode} - ${response.result}`);
      }

      const data = JSON.parse(response.result);
      const choice = data.choices[0];
      const message = choice.message;

      let toolCalls: LLMToolCall[] | null = null;
      if (message.tool_calls) {
        toolCalls = message.tool_calls.map((tc: Record<string, object>) => ({
          id: tc['id'],
          name: tc['function']['name'],
          arguments: tc['function']['arguments'],
        }));
      }

      return {
        content: message.content || '',
        tool_calls: toolCalls,
        finish_reason: choice.finish_reason || 'stop',
      };
    } finally {
      httpRequest.destroy();
    }
  }

  /**
   * 流式对话（SSE）
   * 返回 AsyncGenerator，逐字 yield
   */
  async *chatStream(
    messages: LLMMessage[],
    tools?: ToolDefinition[],
    temperature?: number,
    maxTokens?: number,
  ): AsyncGenerator<string> {
    const payload: Record<string, object> = {
      model: this.config.model,
      messages: messages.map(m => {
        const msg: Record<string, object> = { role: m.role, content: m.content };
        if (m.tool_calls) msg['tool_calls'] = m.tool_calls;
        if (m.tool_call_id) msg['tool_call_id'] = m.tool_call_id;
        if (m.name) msg['name'] = m.name;
        return msg;
      }),
      temperature: temperature ?? this.config.temperature,
      max_tokens: maxTokens ?? this.config.maxTokens,
      stream: true,
    };

    if (tools && tools.length > 0) {
      payload['tools'] = tools.map(t => ({
        type: 'function',
        function: {
          name: t.name,
          description: t.description,
          parameters: t.parameters,
        },
      }));
    }

    const httpRequest = http.createHttp();
    try {
      const response = await httpRequest.request(`${this.config.baseUrl}/chat/completions`, {
        method: http.RequestMethod.POST,
        header: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.config.apiKey}`,
        },
        extraData: JSON.stringify(payload),
        connectTimeout: 30000,
        readTimeout: 120000,
      });

      if (response.responseCode !== 200) {
        throw new Error(`LLM API error: ${response.responseCode} - ${response.result}`);
      }

      // 解析 SSE 格式
      const lines = response.result.split('\n');
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6);
        if (data === '[DONE]') break;
        try {
          const parsed = JSON.parse(data);
          const delta = parsed.choices?.[0]?.delta;
          if (delta?.content) {
            yield delta.content;
          }
        } catch {
          // 忽略解析错误
        }
      }
    } finally {
      httpRequest.destroy();
    }
  }

  /**
   * 轻量意图检测（max_tokens=50, temp=0）
   */
  async detectIntent(userMessage: string): Promise<Record<string, object> | null> {
    const messages: LLMMessage[] = [
      {
        role: 'system',
        content: '判断用户是否表达了就诊/看医生/复查的意图。只返回JSON：{"visit_intent": true/false, "complaint": "就诊原因"}',
      },
      { role: 'user', content: userMessage },
    ];

    const response = await this.chat(messages, undefined, 0, 50);
    try {
      return JSON.parse(response.content);
    } catch {
      return null;
    }
  }
}

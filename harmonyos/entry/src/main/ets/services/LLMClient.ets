/**
 * LLM 客户端服务
 * 
 * 通过 HTTP 调用云端 LLM API（OpenAI 兼容格式）
 * 支持：对话、流式输出（回调）、工具调用
 * 
 * ArkTS 限制：
 * - 不支持 async generator → 使用回调函数
 * - 不支持 Record<K,V> → 使用 interface + Map
 * - response.result 类型是 string | Object | ArrayBuffer → 需要显式处理
 */

import http from '@ohos.net.http';
import { LLMMessage, LLMResponse, LLMToolCall, LLMToolCallFunction } from '../models/HealthModels';

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
// 工具定义
// ============================================================

export interface ToolParameter {
  type: string;
  description: string;
}

export interface ToolParameters {
  type: string;
  properties: Map<string, ToolParameter>;
  required: string[];
}

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: ToolParameters;
}

interface ToolFunctionDef {
  type: string;
  function: ToolFunctionBody;
}

interface ToolFunctionBody {
  name: string;
  description: string;
  parameters: ToolParameters;
}

// ============================================================
// HTTP 消息体
// ============================================================

interface HttpMessage {
  role: string;
  content: string;
  tool_calls?: LLMToolCall[];
  tool_call_id?: string;
  name?: string;
}

interface ChatPayload {
  model: string;
  messages: HttpMessage[];
  temperature: number;
  max_tokens: number;
  tools?: ToolFunctionDef[];
  stream?: boolean;
}

// ============================================================
// API 响应解析
// ============================================================

interface APIChoice {
  index: number;
  message: APIMessage;
  finish_reason: string;
}

interface APIMessage {
  role: string;
  content: string | null;
  tool_calls?: APIToolCall[];
}

interface APIToolCall {
  id: string;
  type: string;
  function: APIFunction;
}

interface APIFunction {
  name: string;
  arguments: string;
}

interface APIResponse {
  choices: APIChoice[];
}

// SSE delta 解析
interface SSEChoice {
  delta: SSEDelta;
}

interface SSEDelta {
  content?: string;
}

interface SSEResponse {
  choices: SSEChoice[];
}

// ============================================================
// LLM 客户端
// ============================================================

export class LLMClient {
  private config: LLMConfig;

  constructor(config: LLMConfig) {
    this.config = config;
  }

  private buildMessages(messages: LLMMessage[]): HttpMessage[] {
    const result: HttpMessage[] = [];
    for (const m of messages) {
      const msg: HttpMessage = { role: m.role, content: m.content };
      if (m.tool_calls) {
        msg.tool_calls = m.tool_calls;
      }
      if (m.tool_call_id) {
        msg.tool_call_id = m.tool_call_id;
      }
      if (m.name) {
        msg.name = m.name;
      }
      result.push(msg);
    }
    return result;
  }

  private buildTools(tools: ToolDefinition[]): ToolFunctionDef[] {
    const result: ToolFunctionDef[] = [];
    for (const t of tools) {
      const fnBody: ToolFunctionBody = {
        name: t.name,
        description: t.description,
        parameters: t.parameters,
      };
      result.push({ type: 'function', function: fnBody });
    }
    return result;
  }

  /**
   * 非流式对话
   */
  async chat(
    messages: LLMMessage[],
    tools: ToolDefinition[] | undefined,
    temperature: number | undefined,
    maxTokens: number | undefined,
  ): Promise<LLMResponse> {
    const payload: ChatPayload = {
      model: this.config.model,
      messages: this.buildMessages(messages),
      temperature: temperature !== undefined ? temperature : this.config.temperature,
      max_tokens: maxTokens !== undefined ? maxTokens : this.config.maxTokens,
    };

    if (tools && tools.length > 0) {
      payload.tools = this.buildTools(tools);
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
        const errBody: string = typeof response.result === 'string' ? response.result : 'non-string error';
        throw new Error(`LLM API error: ${response.responseCode} - ${errBody}`);
      }

      const bodyStr: string = typeof response.result === 'string' ? response.result : '';
      const data: APIResponse = JSON.parse(bodyStr) as APIResponse;
      const choice: APIChoice = data.choices[0];
      const message: APIMessage = choice.message;

      let toolCalls: LLMToolCall[] | null = null;
      if (message.tool_calls && message.tool_calls.length > 0) {
        toolCalls = [];
        for (const tc of message.tool_calls) {
          const fn: LLMToolCallFunction = { name: tc.function.name, arguments: tc.function.arguments };
          toolCalls.push({ id: tc.id, type: tc.type, function: fn });
        }
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
   * 流式对话（回调模式）
   */
  async chatStream(
    messages: LLMMessage[],
    tools: ToolDefinition[] | undefined,
    temperature: number | undefined,
    maxTokens: number | undefined,
    onDelta: (text: string) => void,
  ): Promise<void> {
    const payload: ChatPayload = {
      model: this.config.model,
      messages: this.buildMessages(messages),
      temperature: temperature !== undefined ? temperature : this.config.temperature,
      max_tokens: maxTokens !== undefined ? maxTokens : this.config.maxTokens,
      stream: true,
    };

    if (tools && tools.length > 0) {
      payload.tools = this.buildTools(tools);
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
        const errBody: string = typeof response.result === 'string' ? response.result : 'non-string error';
        throw new Error(`LLM API error: ${response.responseCode} - ${errBody}`);
      }

      const bodyStr: string = typeof response.result === 'string' ? response.result : '';
      const lines: string[] = bodyStr.split('\n');
      for (const line of lines) {
        if (!line.startsWith('data: ')) {
          continue;
        }
        const data: string = line.slice(6);
        if (data === '[DONE]') {
          break;
        }
        try {
          const parsed: SSEResponse = JSON.parse(data) as SSEResponse;
          if (parsed.choices && parsed.choices.length > 0) {
            const delta: SSEDelta = parsed.choices[0].delta;
            if (delta.content) {
              onDelta(delta.content);
            }
          }
        } catch (e) {
          // 忽略解析错误
        }
      }
    } finally {
      httpRequest.destroy();
    }
  }

  /**
   * 轻量意图检测
   */
  async detectIntent(userMessage: string): Promise<string> {
    const messages: LLMMessage[] = [
      {
        role: 'system',
        content: '判断用户是否表达了就诊/看医生/复查的意图。只返回JSON：{"visit_intent": true/false, "complaint": "就诊原因"}',
      },
      { role: 'user', content: userMessage },
    ];

    const response = await this.chat(messages, undefined, 0, 50);
    return response.content;
  }
}

// ============================================================
// 健康工具定义
// ============================================================

export function getHealthTools(): ToolDefinition[] {
  const tools: ToolDefinition[] = [];

  tools.push({
    name: 'query_metrics',
    description: '查询家庭成员的健康指标记录（如血压、血糖、血脂等）',
    parameters: {
      type: 'object',
      properties: new Map<string, ToolParameter>([
        ['metric_name', { type: 'string', description: '指标名称' }],
        ['limit', { type: 'integer', description: '返回最近N条记录，默认10' }],
      ]),
      required: [],
    },
  });

  tools.push({
    name: 'query_profile',
    description: '查询家庭成员的诊断、用药、过敏、家族史等基本健康信息',
    parameters: {
      type: 'object',
      properties: new Map<string, ToolParameter>([
        ['info_type', { type: 'string', description: '查询类型：diagnoses, medications, allergies' }],
      ]),
      required: [],
    },
  });

  tools.push({
    name: 'query_abnormal',
    description: '查询家庭成员的异常指标记录',
    parameters: {
      type: 'object',
      properties: new Map<string, ToolParameter>(),
      required: [],
    },
  });

  tools.push({
    name: 'extract_and_save',
    description: '从用户消息中提取健康数据并保存',
    parameters: {
      type: 'object',
      properties: new Map<string, ToolParameter>([
        ['metric_name', { type: 'string', description: '指标名称' }],
        ['value', { type: 'number', description: '数值' }],
        ['unit', { type: 'string', description: '单位' }],
      ]),
      required: ['metric_name', 'value'],
    },
  });

  tools.push({
    name: 'assess_scale',
    description: '调用健康量表评估',
    parameters: {
      type: 'object',
      properties: new Map<string, ToolParameter>([
        ['scale_code', { type: 'string', description: '量表代码：phq9, gad7, diabetes等' }],
      ]),
      required: ['scale_code'],
    },
  });

  return tools;
}

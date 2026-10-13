/**
 * LLM 客户端服务
 * 
 * 通过 HTTP 调用云端 LLM API（OpenAI 兼容格式）
 * 支持：对话、流式输出（回调）、工具调用
 * 
 * 注意：ArkTS 不支持 async generator，流式输出使用回调函数
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

// ============================================================
// 消息构建辅助
// ============================================================

interface HttpMessage {
  role: string;
  content: string;
  tool_calls?: object;
  tool_call_id?: string;
  name?: string;
}

interface ChatPayload {
  model: string;
  messages: HttpMessage[];
  temperature: number;
  max_tokens: number;
  tools?: object[];
  stream?: boolean;
}

// ============================================================
// LLM 客户端
// ============================================================

export class LLMClient {
  private config: LLMConfig;

  constructor(config: LLMConfig) {
    this.config = config;
  }

  /**
   * 构建消息体
   */
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

  /**
   * 构建工具列表
   */
  private buildTools(tools: ToolDefinition[]): object[] {
    return tools.map((t: ToolDefinition) => {
      return {
        type: 'function',
        function: {
          name: t.name,
          description: t.description,
          parameters: t.parameters,
        },
      };
    });
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
        throw new Error(`LLM API error: ${response.responseCode} - ${response.result}`);
      }

      const data = JSON.parse(response.result);
      const choice = data.choices[0];
      const message = choice.message;

      let toolCalls: LLMToolCall[] | null = null;
      if (message.tool_calls) {
        const rawCalls = message.tool_calls as object[];
        toolCalls = rawCalls.map((tc: object) => {
          const tcObj = tc as Record<string, string>;
          const func = tcObj['function'] as Record<string, string>;
          return {
            id: tcObj['id'],
            name: func['name'],
            arguments: func['arguments'],
          } as LLMToolCall;
        });
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
   * 流式对话（回调模式，因 ArkTS 不支持 async generator）
   * @param onDelta 每收到一段文本时的回调
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
        throw new Error(`LLM API error: ${response.responseCode} - ${response.result}`);
      }

      // 解析 SSE 格式
      const lines = response.result.split('\n');
      for (const line of lines) {
        if (!line.startsWith('data: ')) {
          continue;
        }
        const data = line.slice(6);
        if (data === '[DONE]') {
          break;
        }
        try {
          const parsed = JSON.parse(data);
          const choices = parsed.choices as object[];
          if (choices && choices.length > 0) {
            const delta = (choices[0] as Record<string, object>)['delta'] as Record<string, string>;
            if (delta && delta.content) {
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
   * 轻量意图检测（max_tokens=50, temp=0）
   */
  async detectIntent(userMessage: string): Promise<string | null> {
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
// 健康工具定义（对齐后端 tool registry）
// ============================================================

export function getHealthTools(): ToolDefinition[] {
  return [
    {
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
    },
    {
      name: 'query_profile',
      description: '查询家庭成员的诊断、用药、过敏、家族史等基本健康信息',
      parameters: {
        type: 'object',
        properties: new Map<string, ToolParameter>([
          ['info_type', { type: 'string', description: '查询类型：diagnoses, medications, allergies' }],
        ]),
        required: [],
      },
    },
    {
      name: 'query_abnormal',
      description: '查询家庭成员的异常指标记录',
      parameters: {
        type: 'object',
        properties: new Map<string, ToolParameter>(),
        required: [],
      },
    },
    {
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
    },
    {
      name: 'assess_scale',
      description: '调用健康量表评估',
      parameters: {
        type: 'object',
        properties: new Map<string, ToolParameter>([
          ['scale_code', { type: 'string', description: '量表代码：phq9, gad7, diabetes等' }],
        ]),
        required: ['scale_code'],
      },
    },
  ];
}

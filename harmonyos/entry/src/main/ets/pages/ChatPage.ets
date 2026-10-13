/**
 * 对话页 — AI 健康管家聊天界面
 * 
 * 功能：
 * - 显示对话历史（用户 + AI + 主动消息）
 * - 流式输出 AI 回复
 * - 主动消息标记 + 操作按钮（回复/推迟/忽略）
 * - 风险级别标识
 * - 指标录入
 */

import { ChatMessage, RiskLevel, Priority } from '../models/HealthModels';
import { ConsultationService } from '../services/ConsultationService';

@Entry
@Component
struct Index {
  @State messages: ChatMessage[] = [];
  @State inputText: string = '';
  @State isStreaming: boolean = false;
  @State streamingContent: string = '';
  @State currentMemberId: number = 1;
  @State error: string = '';
  @State currentRiskLevel: RiskLevel | null = null;
  @State isHighRiskAlert: boolean = false;
  @State toolCallBadges: string[] = [];

  private consultationService: ConsultationService | null = null;
  private scroller: Scroller = new Scroller();

  aboutToAppear() {
    // 初始化服务（实际使用时从 Ability 传入 context）
    // this.consultationService = new ConsultationService(db, llm);
    this.loadHistory();
  }

  async loadHistory() {
    if (!this.consultationService) return;
    // 从数据库加载历史消息
    // const history = await this.consultationService.getHistory(this.currentMemberId, 50);
    // this.messages = history;
  }

  async sendMessage() {
    const text = this.inputText.trim();
    if (!text || this.isStreaming || !this.consultationService) return;

    this.inputText = '';
    this.isStreaming = true;
    this.streamingContent = '';
    this.error = '';
    this.currentRiskLevel = null;
    this.isHighRiskAlert = false;
    this.toolCallBadges = [];

    // 添加用户消息
    const userMsg: ChatMessage = {
      id: 0,
      member_id: this.currentMemberId,
      role: 'user',
      content: text,
      source: 'webui',
      message_type: 'normal',
      metadata: null,
      created_at: new Date().toISOString(),
    };
    this.messages.push(userMsg);

    try {
      let fullContent = '';
      
      // 流式输出
      for await (const chunk of this.consultationService.chatStream(this.currentMemberId, text)) {
        if (chunk.type === 'delta') {
          fullContent += chunk.data;
          this.streamingContent = fullContent;
        } else if (chunk.type === 'risk') {
          const riskData = JSON.parse(chunk.data);
          this.currentRiskLevel = riskData.risk_level;
          this.isHighRiskAlert = riskData.risk_level === 'S' || riskData.risk_level === 'A';
          if (riskData.tool_calls) {
            this.toolCallBadges = riskData.tool_calls.map((tc: Record<string, object>) => {
              const labels: Record<string, string> = {
                query_metrics: '已查询健康指标',
                query_profile: '已查询诊断/用药',
                query_abnormal: '已查询异常指标',
                extract_and_save: '已记录健康数据',
                assess_scale: '已调用量表',
              };
              return labels[tc['name'] as string] || tc['name'] as string;
            });
          }
        }
      }

      // 添加 AI 消息
      const aiMsg: ChatMessage = {
        id: 0,
        member_id: this.currentMemberId,
        role: 'assistant',
        content: fullContent || '(空回复)',
        source: 'webui',
        message_type: 'normal',
        metadata: null,
        created_at: new Date().toISOString(),
      };
      this.messages.push(aiMsg);
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'AI 服务暂时不可用';
    } finally {
      this.isStreaming = false;
      this.streamingContent = '';
    }
  }

  build() {
    Column() {
      // 顶部标题栏
      Row() {
        Text('AI 健康管家')
          .fontSize(20)
          .fontWeight(FontWeight.Bold)
          .fontColor('#1a1a1a')
        Blank()
        Text(this.currentRiskLevel ? `风险: ${this.currentRiskLevel}` : '')
          .fontSize(12)
          .fontColor(this.currentRiskLevel === 'S' ? '#dc2626' : 
                     this.currentRiskLevel === 'A' ? '#d97706' : '#16a34a')
      }
      .width('100%')
      .height(56)
      .padding({ left: 16, right: 16 })
      .backgroundColor('#ffffff')
      .border({ bottom: { width: 1, color: '#e2e8f0' } })

      // 高风险横幅
      if (this.isHighRiskAlert) {
        Row() {
          Text('⚠️ 建议立即就医')
            .fontSize(14)
            .fontColor('#ffffff')
            .fontWeight(FontWeight.Medium)
        }
        .width('100%')
        .height(32)
        .backgroundColor('#dc2626')
        .justifyContent(FlexAlign.Center)
      }

      // 消息列表
      List({ scroller: this.scroller }) {
        ForEach(this.messages, (msg: ChatMessage, index: number) => {
          ListItem() {
            this.MessageBubble(msg)
          }
        })

        // 流式输出中的消息
        if (this.isStreaming) {
          ListItem() {
            this.StreamingBubble()
          }
        }

        // 错误提示
        if (this.error) {
          ListItem() {
            Row() {
              Text(this.error)
                .fontSize(14)
                .fontColor('#dc2626')
            }
            .width('100%')
            .padding(12)
            .backgroundColor('#fef2f2')
            .borderRadius(8)
          }
        }
      }
      .layoutWeight(1)
      .width('100%')
      .padding({ left: 12, right: 12 })

      // 输入区
      Row() {
        TextInput({
          text: this.inputText,
          placeholder: '输入健康问题或记录数据...',
        })
          .layoutWeight(1)
          .height(40)
          .fontSize(15)
          .borderRadius(20)
          .backgroundColor('#f1f5f9')
          .onChange((value: string) => {
            this.inputText = value;
          })
          .onSubmit(() => {
            this.sendMessage();
          })

        Button('发送')
          .height(40)
          .margin({ left: 8 })
          .enabled(!this.isStreaming && this.inputText.trim().length > 0)
          .onClick(() => {
            this.sendMessage();
          })
      }
      .width('100%')
      .padding({ left: 12, right: 12, top: 8, bottom: 8 })
      .backgroundColor('#ffffff')
      .border({ top: { width: 1, color: '#e2e8f0' } })
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#f8fafc')
  }

  @Builder
  MessageBubble(msg: ChatMessage) {
    if (msg.role === 'user') {
      // 用户消息：右对齐
      Row() {
        Column() {
          Text(msg.content)
            .fontSize(15)
            .fontColor('#ffffff')
            .padding(12)
            .borderRadius(12)
            .backgroundColor('#2563eb')
        }
        .alignItems(HorizontalAlign.End)
      }
      .width('100%')
      .justifyContent(FlexAlign.End)
      .margin({ bottom: 12 })
    } else {
      // AI 消息：左对齐
      Row() {
        Column() {
          // 主动消息标记
          if (msg.source === 'proactive') {
            Row() {
              Text('🔔 主动健康提醒')
                .fontSize(12)
                .fontColor('#2563eb')
                .backgroundColor('#dbeafe')
                .padding({ left: 8, right: 8, top: 4, bottom: 4 })
                .borderRadius(8)
            }
            .margin({ bottom: 8 })
          }

          // 工具调用徽章
          if (msg.metadata && (msg.metadata as Record<string, object>)['tool_calls']) {
            // TODO: 显示工具调用徽章
          }

          // 消息内容
          Text(msg.content)
            .fontSize(15)
            .fontColor('#1e293b')
            .padding(12)
            .borderRadius(12)
            .backgroundColor('#ffffff')
            .border({ width: 1, color: '#e2e8f0' })

          // 时间
          Text(this.formatTime(msg.created_at))
            .fontSize(11)
            .fontColor('#94a3b8')
            .margin({ top: 4 })
        }
        .alignItems(HorizontalAlign.Start)
      }
      .width('100%')
      .justifyContent(FlexAlign.Start)
      .margin({ bottom: 12 })
    }
  }

  @Builder
  StreamingBubble() {
    Row() {
      Column() {
        Text(this.streamingContent || 'AI 思考中...')
          .fontSize(15)
          .fontColor('#1e293b')
          .padding(12)
          .borderRadius(12)
          .backgroundColor('#ffffff')
          .border({ width: 1, color: '#e2e8f0' })
      }
      .alignItems(HorizontalAlign.Start)
    }
    .width('100%')
    .justifyContent(FlexAlign.Start)
    .margin({ bottom: 12 })
  }

  private formatTime(isoString: string): string {
    const d = new Date(isoString);
    const h = d.getHours().toString().padStart(2, '0');
    const m = d.getMinutes().toString().padStart(2, '0');
    return `${h}:${m}`;
  }
}

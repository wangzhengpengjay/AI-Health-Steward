/**
 * 对话页 — AI 健康管家聊天界面
 * 
 * 功能：
 * - 显示对话历史（用户 + AI + 主动消息）
 * - 流式输出 AI 回复
 * - 主动消息标记 + 操作按钮
 * - 风险级别标识
 * 
 * ArkTS 限制：
 * - 不支持 for await → 使用回调函数
 * - 不支持 Record<K,V> → 使用 Map 或 interface
 * - border 不支持嵌套对象 → 使用 BorderOptions 接口
 */

import { ChatMessage, RiskLevel } from '../models/HealthModels';
import { ConsultationService } from '../services/ConsultationService';
import { DatabaseService } from '../services/DatabaseService';
import { LLMClient, LLMConfig } from '../services/LLMClient';
import { relationalStore } from '@kit.ArkData';
import common from '@ohos.app.ability.common';

interface ToolCallLabel {
  key: string;
  label: string;
}

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
    this.initServices();
  }

  private async initServices(): Promise<void> {
    try {
      const context: common.UIAbilityContext = getContext(this) as common.UIAbilityContext;
      const db: DatabaseService = DatabaseService.getInstance(context);
      await db.init();

      // TODO: 实际应从安全存储中读取 API Key
      const config: LLMConfig = {
        baseUrl: 'https://api.deepseek.com/v1',
        apiKey: 'sk-1e018e6d6ae4429fa3b069cbe5900cb9',
        model: 'deepseek-flash',
        temperature: 0.7,
        maxTokens: 4096,
      };
      const llm: LLMClient = new LLMClient(config);
      this.consultationService = new ConsultationService(db, llm);

      // 首次启动自动创建默认成员
      await this.ensureDefaultMember(db);

      await this.loadHistory();
    } catch (e) {
      this.error = `初始化失败: ${e}`;
    }
  }

  private async ensureDefaultMember(db: DatabaseService): Promise<void> {
    try {
      const rs = await db.query(`SELECT COUNT(*) as cnt FROM family_members WHERE is_deleted = 0`, []);
      const rows = await db.resultSetToArray(rs);
      const count = rows.length > 0 ? rows[0].get('cnt') : 0;
      if (count === 0) {
        const bucket: relationalStore.ValuesBucket = {
          name: '默认成员',
          relationship: 'self',
          birth_date: '1990-01-01',
          gender: 'unknown',
          is_deleted: 0,
        } as relationalStore.ValuesBucket;
        const memberId: number = await db.insert('family_members', bucket);
        this.currentMemberId = memberId;
        console.info(`[Index] Created default member: ${memberId}`);
      } else {
        const idVal = rows[0].get('cnt');
        // 用第一条成员的 ID
        const rs2 = await db.query(`SELECT id FROM family_members WHERE is_deleted = 0 LIMIT 1`, []);
        const rows2 = await db.resultSetToArray(rs2);
        if (rows2.length > 0) {
          const id = rows2[0].get('id');
          if (id !== null && typeof id === 'number') {
            this.currentMemberId = id;
          }
        }
      }
    } catch (e) {
      console.error('[Index] Failed to ensure default member:', e);
    }
  }

  async loadHistory(): Promise<void> {
    if (!this.consultationService) {
      return;
    }
    // TODO: 从数据库加载历史消息
  }

  async sendMessage(): Promise<void> {
    const text: string = this.inputText.trim();
    if (!text || this.isStreaming || !this.consultationService) {
      return;
    }

    this.inputText = '';
    this.isStreaming = true;
    this.streamingContent = '';
    this.error = '';
    this.currentRiskLevel = null;
    this.isHighRiskAlert = false;
    this.toolCallBadges = [];

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
      let fullContent: string = '';

      await this.consultationService.chatStream(
        this.currentMemberId,
        text,
        'webui',
        (delta: string) => {
          fullContent += delta;
          this.streamingContent = fullContent;
        },
        (riskLevel: RiskLevel, toolCallNames: string[]) => {
          this.currentRiskLevel = riskLevel;
          this.isHighRiskAlert = riskLevel === 'S' || riskLevel === 'A';

          const labels: ToolCallLabel[] = [
            { key: 'query_metrics', label: '已查询健康指标' },
            { key: 'query_profile', label: '已查询诊断/用药' },
            { key: 'query_abnormal', label: '已查询异常指标' },
            { key: 'extract_and_save', label: '已记录健康数据' },
            { key: 'assess_scale', label: '已调用量表' },
          ];

          const badges: string[] = [];
          for (const name of toolCallNames) {
            let found: string = name;
            for (const l of labels) {
              if (l.key === name) {
                found = l.label;
                break;
              }
            }
            badges.push(found);
          }
          this.toolCallBadges = badges;
        },
      );

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
      .borderWidth({ bottom: 1 })
      .borderColor('#e2e8f0')

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

        if (this.isStreaming) {
          ListItem() {
            this.StreamingBubble()
          }
        }

        if (this.error.length > 0) {
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
      .borderWidth({ top: 1 })
      .borderColor('#e2e8f0')
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#f8fafc')
  }

  @Builder
  MessageBubble(msg: ChatMessage) {
    if (msg.role === 'user') {
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
      Row() {
        Column() {
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

          Text(msg.content)
            .fontSize(15)
            .fontColor('#1e293b')
            .padding(12)
            .borderRadius(12)
            .backgroundColor('#ffffff')
            .borderWidth(1)
            .borderColor('#e2e8f0')

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
        Text(this.streamingContent.length > 0 ? this.streamingContent : 'AI 思考中...')
          .fontSize(15)
          .fontColor('#1e293b')
          .padding(12)
          .borderRadius(12)
          .backgroundColor('#ffffff')
          .borderWidth(1)
          .borderColor('#e2e8f0')
      }
      .alignItems(HorizontalAlign.Start)
    }
    .width('100%')
    .justifyContent(FlexAlign.Start)
    .margin({ bottom: 12 })
  }

  private formatTime(isoString: string): string {
    const d: Date = new Date(isoString);
    const h: string = d.getHours().toString().padStart(2, '0');
    const m: string = d.getMinutes().toString().padStart(2, '0');
    return `${h}:${m}`;
  }
}

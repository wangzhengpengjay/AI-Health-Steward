/**
 * 代理提醒服务（Reminder Agent）
 * 
 * 使用 @kit.BackgroundTasksKit 的 reminderAgentManager
 * App 被杀也能弹通知，用户点击通知可拉起 App
 * 
 * ⚠️ 需申请权限：ohos.permission.PUBLISH_AGENT_REMINDER
 * ⚠️ 需在 AppGallery Connect 申请开放能力（运动健康类应用可申请，审核约8工作日）
 */

import { reminderAgentManager } from '@kit.BackgroundTasksKit';
import { notificationManager } from '@kit.NotificationKit';
import { ReminderInfo } from '../models/HealthModels';

export class ReminderService {
  private static instance: ReminderService | null = null;

  private constructor() {}

  static getInstance(): ReminderService {
    if (!ReminderService.instance) {
      ReminderService.instance = new ReminderService();
    }
    return ReminderService.instance;
  }

  /**
   * 请求通知授权
   */
  async requestNotificationPermission(): Promise<boolean> {
    try {
      await notificationManager.requestEnableNotification();
      return true;
    } catch (e) {
      console.error('[ReminderService] Failed to request notification permission:', e);
      return false;
    }
  }

  /**
   * 发布定时提醒（日历类型）
   * @param title 提醒标题
   * @param content 提醒内容
   * @param dateTime 提醒时间 { year, month, day, hour, minute }
   * @returns reminderId
   */
  async publishCalendarReminder(
    title: string,
    content: string,
    dateTime: { year: number; month: number; day: number; hour: number; minute: number },
  ): Promise<number> {
    const reminderRequest: reminderAgentManager.ReminderRequestCalendar = {
      reminderType: reminderAgentManager.ReminderType.REMINDER_TYPE_CALENDAR,
      dateTime: dateTime,
      title: title,
      content: content,
      slotType: notificationManager.SlotType.CONTENT_INFORMATION,
      // 点击通知后拉起 App
      actionButton: [
        {
          title: '查看详情',
          type: reminderAgentManager.ActionButtonType.ACTION_BUTTON_TYPE_CLOSE,
        },
      ],
      wantAgent: {
        pkgName: 'com.example.healthsteward',
        abilityName: 'EntryAbility',
      },
    };

    const reminderId = await reminderAgentManager.publishReminder(reminderRequest);
    console.info(`[ReminderService] Published reminder ${reminderId}: ${title}`);
    return reminderId;
  }

  /**
   * 发布倒计时提醒
   * @param title 提醒标题
   * @param content 提醒内容
   * @param seconds 倒计时秒数
   * @returns reminderId
   */
  async publishTimerReminder(title: string, content: string, seconds: number): Promise<number> {
    const reminderRequest: reminderAgentManager.ReminderRequestTimer = {
      reminderType: reminderAgentManager.ReminderType.REMINDER_TYPE_TIMER,
      triggerTimeInSeconds: seconds,
      title: title,
      content: content,
      slotType: notificationManager.SlotType.CONTENT_INFORMATION,
      actionButton: [
        {
          title: '查看详情',
          type: reminderAgentManager.ActionButtonType.ACTION_BUTTON_TYPE_CLOSE,
        },
      ],
      wantAgent: {
        pkgName: 'com.example.healthsteward',
        abilityName: 'EntryAbility',
      },
    };

    const reminderId = await reminderAgentManager.publishReminder(reminderRequest);
    console.info(`[ReminderService] Published timer reminder ${reminderId}: ${title}`);
    return reminderId;
  }

  /**
   * 取消提醒
   */
  async cancelReminder(reminderId: number): Promise<void> {
    await reminderAgentManager.cancelReminder(reminderId);
    console.info(`[ReminderService] Cancelled reminder ${reminderId}`);
  }

  /**
   * 取消所有提醒
   */
  async cancelAllReminders(): Promise<void> {
    await reminderAgentManager.cancelAllReminders();
    console.info('[ReminderService] Cancelled all reminders');
  }

  /**
   * 获取所有有效提醒
   */
  async getValidReminders(): Promise<reminderAgentManager.ReminderRequest[]> {
    return await reminderAgentManager.getValidReminders();
  }

  /**
   * 为主动健康消息创建提醒
   * 紧急消息：1分钟后提醒
   * 普通消息：次日早上9点提醒
   */
  async scheduleProactiveReminder(
    message: string,
    priority: 'critical' | 'high' | 'normal',
  ): Promise<number | null> {
    const title = 'AI健康管家提醒';

    if (priority === 'critical') {
      // 紧急：1分钟后提醒
      return await this.publishTimerReminder(title, message, 60);
    }

    // 非紧急：次日早上9点
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    return await this.publishCalendarReminder(title, message, {
      year: tomorrow.getFullYear(),
      month: tomorrow.getMonth() + 1,
      day: tomorrow.getDate(),
      hour: 9,
      minute: 0,
    });
  }
}

/**
 * 代理提醒服务（Reminder Agent）
 * 
 * 使用 @kit.BackgroundTasksKit 的 reminderAgentManager
 * App 被杀也能弹通知，用户点击通知可拉起 App
 * 
 * ⚠️ 需申请权限：ohos.permission.PUBLISH_AGENT_REMINDER
 */

import { reminderAgentManager } from '@kit.BackgroundTasksKit';
import { notificationManager } from '@kit.NotificationKit';

// ============================================================
// 接口定义（ArkTS 不支持匿名 object 字面量）
// ============================================================

interface DateTimeInfo {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
}

interface WantAgentInfo {
  pkgName: string;
  abilityName: string;
}

// ============================================================
// 提醒服务
// ============================================================

export class ReminderService {
  private static instance: ReminderService | null = null;

  private constructor() {}

  static getInstance(): ReminderService {
    if (!ReminderService.instance) {
      ReminderService.instance = new ReminderService();
    }
    return ReminderService.instance;
  }

  async requestNotificationPermission(): Promise<boolean> {
    try {
      await notificationManager.requestEnableNotification();
      return true;
    } catch (e) {
      console.error('[ReminderService] Failed to request notification permission:', e);
      return false;
    }
  }

  async publishCalendarReminder(
    title: string,
    content: string,
    dateTime: DateTimeInfo,
  ): Promise<number> {
    const button: reminderAgentManager.ActionButton = {
      title: '查看详情',
      type: reminderAgentManager.ActionButtonType.ACTION_BUTTON_TYPE_CLOSE,
    };
    const want: WantAgentInfo = { pkgName: 'com.example.healthsteward', abilityName: 'EntryAbility' };

    const reminderRequest: reminderAgentManager.ReminderRequestCalendar = {
      reminderType: reminderAgentManager.ReminderType.REMINDER_TYPE_CALENDAR,
      dateTime: dateTime,
      title: title,
      content: content,
      slotType: notificationManager.SlotType.CONTENT_INFORMATION,
      actionButton: [button],
      wantAgent: want,
    };

    const reminderId: number = await reminderAgentManager.publishReminder(reminderRequest);
    console.info(`[ReminderService] Published reminder ${reminderId}: ${title}`);
    return reminderId;
  }

  async publishTimerReminder(title: string, content: string, seconds: number): Promise<number> {
    const button: reminderAgentManager.ActionButton = {
      title: '查看详情',
      type: reminderAgentManager.ActionButtonType.ACTION_BUTTON_TYPE_CLOSE,
    };
    const want: WantAgentInfo = { pkgName: 'com.example.healthsteward', abilityName: 'EntryAbility' };

    const reminderRequest: reminderAgentManager.ReminderRequestTimer = {
      reminderType: reminderAgentManager.ReminderType.REMINDER_TYPE_TIMER,
      triggerTimeInSeconds: seconds,
      title: title,
      content: content,
      slotType: notificationManager.SlotType.CONTENT_INFORMATION,
      actionButton: [button],
      wantAgent: want,
    };

    const reminderId: number = await reminderAgentManager.publishReminder(reminderRequest);
    console.info(`[ReminderService] Published timer reminder ${reminderId}: ${title}`);
    return reminderId;
  }

  async cancelReminder(reminderId: number): Promise<void> {
    await reminderAgentManager.cancelReminder(reminderId);
    console.info(`[ReminderService] Cancelled reminder ${reminderId}`);
  }

  async cancelAllReminders(): Promise<void> {
    await reminderAgentManager.cancelAllReminders();
    console.info('[ReminderService] Cancelled all reminders');
  }

  async getValidReminders(): Promise<reminderAgentManager.ReminderRequest[]> {
    return await reminderAgentManager.getValidReminders();
  }

  async scheduleProactiveReminder(
    message: string,
    priority: 'critical' | 'high' | 'normal',
  ): Promise<number | null> {
    const title: string = 'AI健康管家提醒';

    if (priority === 'critical') {
      return await this.publishTimerReminder(title, message, 60);
    }

    const tomorrow: Date = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const dt: DateTimeInfo = {
      year: tomorrow.getFullYear(),
      month: tomorrow.getMonth() + 1,
      day: tomorrow.getDate(),
      hour: 9,
      minute: 0,
    };
    return await this.publishCalendarReminder(title, message, dt);
  }
}

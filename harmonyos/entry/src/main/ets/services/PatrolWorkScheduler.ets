/**
 * 延迟任务（Work Scheduler）— 后台定时巡检
 * 
 * 使用 @kit.BackgroundTasksKit 的 WorkScheduler
 * 最小间隔 20 分钟，系统按条件调度
 * 需在 module.json5 中注册
 */

import { WorkSchedulerExtensionAbility, workScheduler } from '@kit.BackgroundTasksKit';
import { DatabaseService } from './DatabaseService';
import { LLMClient } from './LLMClient';
import { PatrolEngine } from './PatrolEngine';
import { ReminderService } from './ReminderService';

export class PatrolWorkScheduler extends WorkSchedulerExtensionAbility {
  onWorkStart(workInfo: workScheduler.WorkInfo) {
    console.info(`[PatrolWorkScheduler] Work started: ${JSON.stringify(workInfo)}`);

    // 异步执行巡检
    this.runPatrol().catch((e: Error) => {
      console.error('[PatrolWorkScheduler] Patrol failed:', e);
    });
  }

  onWorkStop(workInfo: workScheduler.WorkInfo) {
    console.info(`[PatrolWorkScheduler] Work stopped: ${JSON.stringify(workInfo)}`);
  }

  /**
   * 执行巡检逻辑
   */
  private async runPatrol(): Promise<void> {
    // 1. 初始化数据库
    const context = this.context;
    const db = DatabaseService.getInstance(context);
    await db.init();

    // 2. 初始化 LLM 客户端
    // TODO: 从配置文件读取
    const llm = new LLMClient({
      baseUrl: 'https://api.deepseek.com/v1',
      apiKey: '', // 从配置读取
      model: 'deepseek-flash',
      temperature: 0.7,
      maxTokens: 4096,
    });

    // 3. 初始化巡检引擎
    const patrol = new PatrolEngine(db, llm);

    // 4. 遍历所有成员执行巡检
    const rs = await db.query(
      `SELECT id FROM family_members WHERE is_deleted = 0`,
      []
    );
    const members = db.resultSetToArray(rs);

    for (const member of members) {
      const memberId = member['id'] as number;
      try {
        const result = await patrol.patrolMember(memberId, 'scheduled');

        if (result.should_push && result.message) {
          // 保存主动消息
          await patrol.saveProactiveMessage(memberId, result.message, result.priority, result.patrol_id);

          // 保存任务
          if (result.tasks.length > 0) {
            await patrol.saveTasks(memberId, result.tasks);
          }

          // 设置提醒通知
          const reminder = ReminderService.getInstance();
          await reminder.scheduleProactiveReminder(result.message, result.priority);
        }
      } catch (e) {
        console.error(`[PatrolWorkScheduler] Patrol failed for member ${memberId}:`, e);
      }
    }

    console.info('[PatrolWorkScheduler] Patrol completed for all members');
  }
}

/**
 * 注册延迟巡检任务
 * 在 App 启动时调用
 */
export async function registerPatrolWork(): Promise<void> {
  const workInfo: workScheduler.WorkInfo = {
    workId: 1,
    networkType: workScheduler.NetworkType.NETWORK_TYPE_ANY,
    bundleName: 'com.example.healthsteward',
    abilityName: 'PatrolWorkScheduler',
  };

  await workScheduler.startWork(workInfo);
  console.info('[PatrolWorkScheduler] Registered patrol work scheduler');
}

/**
 * 取消延迟巡检任务
 */
export async function unregisterPatrolWork(): Promise<void> {
  const workInfo: workScheduler.WorkInfo = {
    workId: 1,
    bundleName: 'com.example.healthsteward',
    abilityName: 'PatrolWorkScheduler',
  };

  await workScheduler.stopWork(workInfo);
  console.info('[PatrolWorkScheduler] Unregistered patrol work scheduler');
}

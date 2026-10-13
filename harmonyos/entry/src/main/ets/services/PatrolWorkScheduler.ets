/**
 * 延迟任务（Work Scheduler）— 后台定时巡检
 * 
 * 使用 @kit.BackgroundTasksKit 的 WorkScheduler
 * 最小间隔 20 分钟，系统按条件调度
 * 需在 module.json5 中注册
 * 
 * ArkTS 限制：
 * - 不支持 Record<K,V> → 使用 DataRow
 * - 不支持 object 类型 → 使用具体 interface
 */

import { WorkSchedulerExtensionAbility, workScheduler } from '@kit.BackgroundTasksKit';
import { DatabaseService, DataRow, ColumnValue } from './DatabaseService';
import { LLMClient, LLMConfig } from './LLMClient';
import { PatrolEngine } from './PatrolEngine';
import { ReminderService } from './ReminderService';
import { Priority } from '../models/HealthModels';

export class PatrolWorkScheduler extends WorkSchedulerExtensionAbility {
  onWorkStart(workInfo: workScheduler.WorkInfo): void {
    console.info(`[PatrolWorkScheduler] Work started: ${JSON.stringify(workInfo)}`);
    this.runPatrol().catch((e: Error) => {
      console.error('[PatrolWorkScheduler] Patrol failed:', e);
    });
  }

  onWorkStop(workInfo: workScheduler.WorkInfo): void {
    console.info(`[PatrolWorkScheduler] Work stopped: ${JSON.stringify(workInfo)}`);
  }

  private async runPatrol(): Promise<void> {
    const context = this.context;
    const db: DatabaseService = DatabaseService.getInstance(context);
    await db.init();

    const config: LLMConfig = {
      baseUrl: 'https://api.deepseek.com/v1',
      apiKey: '',
      model: 'deepseek-flash',
      temperature: 0.7,
      maxTokens: 4096,
    };
    const llm: LLMClient = new LLMClient(config);
    const patrol: PatrolEngine = new PatrolEngine(db, llm);

    const rs = await db.query(
      `SELECT id FROM family_members WHERE is_deleted = 0`,
      []
    );
    const members: DataRow[] = await db.resultSetToArray(rs);

    for (const member of members) {
      const memberIdVal: ColumnValue | undefined = member.get('id');
      if (memberIdVal === undefined || memberIdVal === null || typeof memberIdVal !== 'number') {
        continue;
      }
      const memberId: number = memberIdVal;

      try {
        const result = await patrol.patrolMember(memberId, 'scheduled');

        if (result.should_push && result.message.length > 0) {
          await patrol.saveProactiveMessage(memberId, result.message, result.priority, result.patrol_id);

          if (result.tasks.length > 0) {
            await patrol.saveTasks(memberId, result.tasks);
          }

          const reminder: ReminderService = ReminderService.getInstance();
          const priority: Priority = result.priority;
          if (priority === 'critical' || priority === 'high' || priority === 'normal') {
            await reminder.scheduleProactiveReminder(result.message, priority);
          }
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

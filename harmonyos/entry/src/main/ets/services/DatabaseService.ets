/**
 * ArkData RDB 数据库服务
 * 
 * 使用 SQLite 内核，SQL 语法与 PostgreSQL 基本兼容
 * 负责所有本地数据的 CRUD 操作
 * 
 * ArkTS 限制：
 * - 不支持 Record<K,V>，resultSet 返回 Map<string, ValueType>
 * - ColumnType 枚举值需要用数字常量
 */

import { relationalStore } from '@kit.ArkData';
import { common } from '@kit.AbilityKit';

const DB_NAME: string = 'health_steward.db';
const DB_SECURITY_LEVEL: relationalStore.SecurityLevel = relationalStore.SecurityLevel.S1;

// ColumnType 常量（避免枚举名不匹配）
const COL_INTEGER: number = 0;
const COL_FLOAT: number = 1;
const COL_STRING: number = 2;
const COL_BLOB: number = 3;
const COL_NULL: number = 4;

// ============================================================
// 建表 SQL
// ============================================================

const CREATE_TABLES_SQL: string[] = [
  `CREATE TABLE IF NOT EXISTS family_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    gender TEXT NOT NULL DEFAULT 'male',
    birth_date TEXT,
    height REAL DEFAULT 0,
    weight REAL DEFAULT 0,
    bmi REAL DEFAULT 0,
    blood_type TEXT,
    relationship TEXT DEFAULT 'self',
    region TEXT,
    occupation TEXT,
    is_pregnant INTEGER DEFAULT 0,
    is_preparing_pregnancy INTEGER DEFAULT 0,
    has_sexual_history INTEGER DEFAULT 0,
    contrast_allergy INTEGER DEFAULT 0,
    has_pacemaker INTEGER DEFAULT 0,
    has_metal_implant INTEGER DEFAULT 0,
    egfr REAL,
    on_anticoagulant INTEGER DEFAULT 0,
    claustrophobia INTEGER DEFAULT 0,
    is_breathing INTEGER DEFAULT 1,
    has_coagulopathy INTEGER DEFAULT 0,
    has_heart_failure INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    memory_summary TEXT,
    memory_summary_updated_at TEXT,
    is_deleted INTEGER DEFAULT 0,
    deleted_at TEXT
  )`,
  `CREATE TABLE IF NOT EXISTS metric_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL,
    text_value TEXT,
    unit TEXT,
    reference_lower REAL,
    reference_upper REAL,
    is_abnormal INTEGER DEFAULT 0,
    is_critical INTEGER DEFAULT 0,
    measured_at TEXT NOT NULL,
    context TEXT,
    source_type TEXT DEFAULT 'manual',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES family_members(id)
  )`,
  `CREATE TABLE IF NOT EXISTS diagnoses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    diagnosis_name TEXT NOT NULL,
    diagnosis_date TEXT,
    hospital TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES family_members(id)
  )`,
  `CREATE TABLE IF NOT EXISTS medications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    drug_name TEXT NOT NULL,
    generic_name TEXT,
    dosage TEXT,
    frequency TEXT,
    route TEXT,
    start_date TEXT,
    end_date TEXT,
    diagnosis_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES family_members(id)
  )`,
  `CREATE TABLE IF NOT EXISTS allergies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    type TEXT,
    name TEXT NOT NULL,
    severity TEXT,
    recorded_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES family_members(id)
  )`,
  `CREATE TABLE IF NOT EXISTS lifestyles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    status TEXT,
    frequency TEXT,
    recorded_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES family_members(id)
  )`,
  `CREATE TABLE IF NOT EXISTS family_histories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    relation TEXT,
    disease_name TEXT NOT NULL,
    recorded_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES family_members(id)
  )`,
  `CREATE TABLE IF NOT EXISTS surgeries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    surgery_name TEXT NOT NULL,
    surgery_date TEXT,
    hospital TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES family_members(id)
  )`,
  `CREATE TABLE IF NOT EXISTS vaccinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    vaccine_name TEXT NOT NULL,
    dose_no INTEGER DEFAULT 1,
    vaccinated_date TEXT,
    facility TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES family_members(id)
  )`,
  `CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT DEFAULT 'webui',
    message_type TEXT DEFAULT 'normal',
    metadata_json TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES family_members(id)
  )`,
  `CREATE TABLE IF NOT EXISTS health_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT DEFAULT 'other',
    urgency TEXT DEFAULT 'normal',
    due_date TEXT,
    status TEXT DEFAULT 'open',
    source TEXT DEFAULT 'manual',
    source_ref TEXT,
    auto_generated INTEGER DEFAULT 0,
    completed_at TEXT,
    dismissed_at TEXT,
    postponed_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES family_members(id)
  )`,
  `CREATE TABLE IF NOT EXISTS checkup_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    report_date TEXT,
    hospital TEXT,
    report_type TEXT,
    raw_text TEXT,
    extraction_json TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES family_members(id)
  )`,
  `CREATE TABLE IF NOT EXISTS health_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL,
    period TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    content TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (member_id) REFERENCES family_members(id)
  )`,
  `CREATE INDEX IF NOT EXISTS idx_metric_member ON metric_records(member_id, measured_at)`,
  `CREATE INDEX IF NOT EXISTS idx_chat_member ON chat_messages(member_id, created_at)`,
  `CREATE INDEX IF NOT EXISTS idx_task_member ON health_tasks(member_id, status)`,
];

// ============================================================
// 行数据类型 — 使用 Map 而非 indexed signature（ArkTS 限制）
export type ColumnValue = number | string | Uint8Array | null;
export type DataRow = Map<string, ColumnValue>;

// ============================================================
// 数据库服务
// ============================================================

export class DatabaseService {
  private static instance: DatabaseService | null = null;
  private store: relationalStore.RdbStore | null = null;
  private context: common.Context;

  private constructor(context: common.Context) {
    this.context = context;
  }

  static getInstance(context: common.Context): DatabaseService {
    if (!DatabaseService.instance) {
      DatabaseService.instance = new DatabaseService(context);
    }
    return DatabaseService.instance;
  }

  async init(): Promise<void> {
    const config: relationalStore.StoreConfig = {
      name: DB_NAME,
      securityLevel: DB_SECURITY_LEVEL,
    };
    this.store = await relationalStore.getRdbStore(this.context, config);
    for (const sql of CREATE_TABLES_SQL) {
      await this.store!.executeSql(sql);
    }
    console.info('[DatabaseService] Database initialized successfully');
  }

  getStore(): relationalStore.RdbStore {
    if (!this.store) {
      throw new Error('Database not initialized. Call init() first.');
    }
    return this.store;
  }

  async insert(table: string, values: relationalStore.ValuesBucket): Promise<number> {
    const store = this.getStore();
    const rowId: number = await store.insert(table, values);
    console.info(`[DatabaseService] Inserted into ${table}, rowId=${rowId}`);
    return rowId;
  }

  async query(sql: string, args: string[]): Promise<relationalStore.ResultSet> {
    const store = this.getStore();
    return await store.querySql(sql, args);
  }

  async execute(sql: string, args: string[]): Promise<void> {
    const store = this.getStore();
    await store.executeSql(sql, args);
  }

  /**
   * 将 ResultSet 转为 DataRow 数组
   */
  resultSetToArray(rs: relationalStore.ResultSet): DataRow[] {
    const results: DataRow[] = [];
    while (rs.goToNextRow()) {
      const row: DataRow = new Map<string, ColumnValue>();
      for (let i = 0; i < rs.columnCount; i++) {
        const colName: string = rs.getColumnName(i);
        const colType: number = rs.getColumnType(i);
        if (colType === COL_INTEGER) {
          row.set(colName, rs.getLong(i));
        } else if (colType === COL_FLOAT) {
          row.set(colName, rs.getDouble(i));
        } else if (colType === COL_STRING) {
          row.set(colName, rs.getString(i));
        } else if (colType === COL_BLOB) {
          row.set(colName, rs.getBlob(i));
        } else {
          row.set(colName, null);
        }
      }
      results.push(row);
    }
    rs.close();
    return results;
  }
}

// ============================================================
// 公共辅助函数（供其他 service 复用，避免重复代码）
// ============================================================

export function getMapVal(row: DataRow, key: string): ColumnValue {
  const v: ColumnValue | undefined = row.get(key);
  return v === undefined ? null : v;
}

export function getMapString(row: DataRow, key: string): string {
  const v: ColumnValue = getMapVal(row, key);
  if (v !== null && typeof v === 'string') {
    return v;
  }
  return '';
}

export function getMapNumber(row: DataRow, key: string): number {
  const v: ColumnValue = getMapVal(row, key);
  if (v !== null && typeof v === 'number') {
    return v;
  }
  return 0;
}

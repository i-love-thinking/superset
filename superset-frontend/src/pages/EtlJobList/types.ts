/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

export type EtlScheduleType = 'cron' | 'onetime';
export type EtlFileType = 'auto' | 'csv' | 'tsv' | 'excel';
export type EtlIfExists = 'fail' | 'replace' | 'append';
export type EtlState = 'success' | 'working' | 'error' | 'pending';

export interface EtlJobSource {
  id?: number;
  url: string;
  order: number;
  sheet_name?: string | null;
  delimiter?: string | null;
  encoding?: string | null;
}

export interface DatabaseSummary {
  id: number;
  database_name: string;
}

export interface UserSummary {
  id: number;
  first_name: string;
  last_name: string;
}

export interface EtlJob {
  id: number;
  uuid: string;
  name: string;
  description?: string | null;
  active: boolean;

  schedule_type: EtlScheduleType;
  crontab?: string | null;
  run_at?: string | null;
  timezone: string;

  database_id: number;
  database?: DatabaseSummary | null;
  target_schema?: string | null;
  target_table: string;

  file_type: EtlFileType;
  if_exists: EtlIfExists;
  dataframe_index: boolean;

  /** JSON-encoded list, e.g. '["col_a", "col_b"]' */
  columns_read?: string | null;
  /** JSON-encoded dict, e.g. '{"amount": "float64"}' */
  column_data_types?: string | null;
  /** JSON-encoded dict, e.g. '{"old": "new"}' */
  column_rename?: string | null;
  /** JSON-encoded dict of HTTP headers */
  http_headers?: string | null;

  last_run_dttm?: string | null;
  last_run_state?: EtlState | null;

  log_retention: number;
  working_timeout: number;

  sources: EtlJobSource[];

  changed_on?: string;
  created_on?: string;
  changed_by?: UserSummary | null;
  created_by?: UserSummary | null;
}

/** Shape of the form values inside EtlJobModal */
export interface EtlJobFormValues {
  name: string;
  description?: string;
  active: boolean;

  schedule_type: EtlScheduleType;
  crontab?: string;
  run_at?: string;
  timezone: string;

  database_id?: number;
  target_schema?: string;
  target_table: string;

  file_type: EtlFileType;
  if_exists: EtlIfExists;
  dataframe_index: boolean;

  /** Parsed from JSON; edited as a list in the UI */
  columns_read?: string[];
  /** Parsed from JSON; edited as [{name, dtype}] in the UI */
  column_data_types?: Array<{ name: string; dtype: string }>;
  /** Parsed from JSON; edited as [{old_name, new_name}] in the UI */
  column_rename?: Array<{ old_name: string; new_name: string }>;
  /** Bearer token or empty string */
  bearer_token?: string;
  /** Extra static HTTP headers besides Authorization */
  extra_headers?: Array<{ key: string; value: string }>;
  /** SMB username (for smb:// sources) */
  smb_username?: string;
  /** SMB password (for smb:// sources) */
  smb_password?: string;
  /** SMB domain / workgroup (optional) */
  smb_domain?: string;
  /** SMB port override (default 445) */
  smb_port?: string;

  sources: EtlJobSource[];

  log_retention: number;
  working_timeout: number;
}

export interface EtlJobLog {
  id: number;
  etl_job_id: number;
  scheduled_dttm?: string | null;
  start_dttm: string;
  end_dttm?: string | null;
  state: EtlState;
  error_message?: string | null;
  rows_imported?: number | null;
  celery_task_id?: string | null;
}

export interface EtlJobListProps {
  addDangerToast: (msg: string) => void;
  addSuccessToast: (msg: string) => void;
}

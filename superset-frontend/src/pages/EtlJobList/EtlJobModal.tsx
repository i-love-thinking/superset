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

/**
 * EtlJobModal
 *
 * Three-step wizard for creating / editing an ETL Job:
 *   Step 1 – Basic Info       (name, description, active, schedule)
 *   Step 2 – Source URLs      (add / remove / reorder URL sources)
 *   Step 3 – Target & Columns (database, table, column filtering/types)
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { SupersetClient, JsonObject } from '@superset-ui/core';
import {
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Steps,
  Switch,
  Tooltip,
} from '@superset-ui/core/components';
import { Icons } from '@superset-ui/core/components/Icons';
import { css, styled } from '@apache-superset/core/theme';
import type {
  EtlFileType,
  EtlIfExists,
  EtlJob,
  EtlJobFormValues,
  EtlJobSource,
  EtlScheduleType,
} from './types';

// ── Helpers ───────────────────────────────────────────────────────────────

function safeParseJson<T>(json: string | null | undefined, fallback: T): T {
  if (!json) return fallback;
  try {
    return JSON.parse(json) as T;
  } catch {
    return fallback;
  }
}

function jobToFormValues(job: EtlJob): EtlJobFormValues {
  const headers: JsonObject = safeParseJson(job.http_headers, {});
  const bearer = (headers['Authorization'] as string | undefined)?.replace(
    'Bearer ',
    '',
  );
  const extraHeaders = Object.entries(headers)
    .filter(([k]) => k !== 'Authorization' && !k.startsWith('smb_'))
    .map(([key, value]) => ({ key, value: String(value) }));

  return {
    name: job.name,
    description: job.description ?? '',
    active: job.active,
    schedule_type: job.schedule_type,
    crontab: job.crontab ?? '',
    run_at: job.run_at ?? '',
    timezone: job.timezone,
    database_id: job.database_id,
    target_schema: job.target_schema ?? '',
    target_table: job.target_table,
    file_type: job.file_type,
    if_exists: job.if_exists,
    dataframe_index: job.dataframe_index,
    columns_read: safeParseJson<string[]>(job.columns_read, []),
    column_data_types: Object.entries(
      safeParseJson<Record<string, string>>(job.column_data_types, {}),
    ).map(([name, dtype]) => ({ name, dtype })),
    column_rename: Object.entries(
      safeParseJson<Record<string, string>>(job.column_rename, {}),
    ).map(([old_name, new_name]) => ({ old_name, new_name })),
    bearer_token: bearer ?? '',
    extra_headers: extraHeaders,
    smb_username: String(headers['smb_username'] ?? ''),
    smb_password: String(headers['smb_password'] ?? ''),
    smb_domain: String(headers['smb_domain'] ?? ''),
    smb_port: String(headers['smb_port'] ?? ''),
    sources: job.sources.map(s => ({ ...s })),
    log_retention: job.log_retention,
    working_timeout: job.working_timeout,
  };
}

function formValuesToPayload(values: EtlJobFormValues): JsonObject {
  // Build http_headers JSON (stores both HTTP auth and SMB credentials)
  const headers: Record<string, string> = {};
  if (values.bearer_token) {
    headers['Authorization'] = `Bearer ${values.bearer_token}`;
  }
  (values.extra_headers ?? []).forEach(({ key, value }) => {
    if (key) headers[key] = value;
  });
  if (values.smb_username) {
    headers['smb_username'] = values.smb_username;
    if (values.smb_password) headers['smb_password'] = values.smb_password;
    if (values.smb_domain) headers['smb_domain'] = values.smb_domain;
    if (values.smb_port) headers['smb_port'] = values.smb_port;
  }

  // Build column_data_types JSON
  const columnDataTypes: Record<string, string> = {};
  (values.column_data_types ?? []).forEach(({ name, dtype }) => {
    if (name && dtype) columnDataTypes[name] = dtype;
  });

  // Build column_rename JSON
  const columnRename: Record<string, string> = {};
  (values.column_rename ?? []).forEach(({ old_name, new_name }) => {
    if (old_name && new_name) columnRename[old_name] = new_name;
  });

  return {
    name: values.name,
    description: values.description || null,
    active: values.active,
    schedule_type: values.schedule_type,
    crontab: values.schedule_type === 'cron' ? values.crontab || null : null,
    run_at: values.schedule_type === 'onetime' ? values.run_at || null : null,
    timezone: values.timezone,
    database_id: values.database_id,
    target_schema: values.target_schema || null,
    target_table: values.target_table,
    file_type: values.file_type,
    if_exists: values.if_exists,
    dataframe_index: values.dataframe_index,
    columns_read:
      (values.columns_read ?? []).length > 0
        ? JSON.stringify(values.columns_read)
        : null,
    column_data_types:
      Object.keys(columnDataTypes).length > 0
        ? JSON.stringify(columnDataTypes)
        : null,
    column_rename:
      Object.keys(columnRename).length > 0
        ? JSON.stringify(columnRename)
        : null,
    http_headers:
      Object.keys(headers).length > 0 ? JSON.stringify(headers) : null,
    sources: values.sources.map((s, idx) => ({ ...s, order: idx })),
    log_retention: values.log_retention,
    working_timeout: values.working_timeout,
  };
}

// ── Styled helpers ────────────────────────────────────────────────────────

const RowFlex = styled.div`
  ${({ theme }) => css`
    display: flex;
    gap: ${theme.gridUnit * 2}px;
    align-items: center;
  `}
`;

const SourceCard = styled.div`
  ${({ theme }) => css`
    border: 1px solid ${theme.colorBorderSecondary};
    border-radius: ${theme.borderRadius}px;
    padding: ${theme.gridUnit * 2}px;
    margin-bottom: ${theme.gridUnit * 2}px;
  `}
`;

const AddButton = styled(Button)`
  margin-top: ${({ theme }) => theme.gridUnit * 2}px;
`;

const EmptySourcesHint = styled.p`
  ${({ theme }) => css`
    color: ${theme.colorTextSecondary};
    font-style: italic;
    margin-bottom: ${theme.gridUnit * 2}px;
  `}
`;

// ── Initial values ────────────────────────────────────────────────────────

const INITIAL_FORM: EtlJobFormValues = {
  name: '',
  description: '',
  active: true,
  schedule_type: 'cron',
  crontab: '0 * * * *',
  run_at: '',
  timezone: 'UTC',
  database_id: undefined as unknown as number,
  target_schema: '',
  target_table: '',
  file_type: 'auto',
  if_exists: 'fail',
  dataframe_index: false,
  columns_read: [],
  column_data_types: [],
  column_rename: [],
  bearer_token: '',
  extra_headers: [],
  smb_username: '',
  smb_password: '',
  smb_domain: '',
  smb_port: '',
  sources: [{ url: '', order: 0 }],
  log_retention: 90,
  working_timeout: 3600,
};

// ── PANDAS_DTYPES for the column-type selector ────────────────────────────

const PANDAS_DTYPES = [
  { label: 'string', value: 'string' },
  { label: 'object', value: 'object' },
  { label: 'int64', value: 'int64' },
  { label: 'int32', value: 'int32' },
  { label: 'float64', value: 'float64' },
  { label: 'float32', value: 'float32' },
  { label: 'bool', value: 'bool' },
  { label: 'datetime64[ns]', value: 'datetime64[ns]' },
  { label: 'category', value: 'category' },
];

// ── Props ─────────────────────────────────────────────────────────────────

interface EtlJobModalProps {
  job: EtlJob | null;
  onHide: () => void;
  onSave: () => void;
  addDangerToast: (msg: string) => void;
  addSuccessToast: (msg: string) => void;
}

// ── Component ─────────────────────────────────────────────────────────────

export default function EtlJobModal({
  job,
  onHide,
  onSave,
  addDangerToast,
  addSuccessToast,
}: EtlJobModalProps) {
  const [step, setStep] = useState(0);
  const [values, setValues] = useState<EtlJobFormValues>(
    job ? jobToFormValues(job) : INITIAL_FORM,
  );
  const [saving, setSaving] = useState(false);
  const [databases, setDatabases] = useState<{ id: number; database_name: string }[]>([]);

  const isEditing = Boolean(job?.id);

  // Reset when job prop changes
  useEffect(() => {
    setValues(job ? jobToFormValues(job) : INITIAL_FORM);
    setStep(0);
  }, [job]);

  // Load available databases
  useEffect(() => {
    SupersetClient.get({ endpoint: '/api/v1/database/?q=(page_size:100)' })
      .then(({ json }) => {
        setDatabases(
          (json as JsonObject).result as { id: number; database_name: string }[],
        );
      })
      .catch(() => addDangerToast(t('Failed to load databases')));
  }, [addDangerToast]);

  // ── Field helpers ──────────────────────────────────────────────────

  const set = useCallback(
    <K extends keyof EtlJobFormValues>(key: K, value: EtlJobFormValues[K]) => {
      setValues(prev => ({ ...prev, [key]: value }));
    },
    [],
  );

  // ── Source helpers ─────────────────────────────────────────────────

  const addSource = useCallback(() => {
    setValues(prev => ({
      ...prev,
      sources: [...prev.sources, { url: '', order: prev.sources.length }],
    }));
  }, []);

  const removeSource = useCallback((idx: number) => {
    setValues(prev => ({
      ...prev,
      sources: prev.sources.filter((_, i) => i !== idx),
    }));
  }, []);

  const setSource = useCallback(
    (idx: number, field: keyof EtlJobSource, value: string | null) => {
      setValues(prev => {
        const sources = prev.sources.map((s, i) =>
          i === idx ? { ...s, [field]: value } : s,
        );
        return { ...prev, sources };
      });
    },
    [],
  );

  // ── Column helpers ─────────────────────────────────────────────────

  const addColumnRead = useCallback(() => {
    set('columns_read', [...(values.columns_read ?? []), '']);
  }, [set, values.columns_read]);

  const addColumnType = useCallback(() => {
    set('column_data_types', [
      ...(values.column_data_types ?? []),
      { name: '', dtype: 'string' },
    ]);
  }, [set, values.column_data_types]);

  const addColumnRename = useCallback(() => {
    set('column_rename', [
      ...(values.column_rename ?? []),
      { old_name: '', new_name: '' },
    ]);
  }, [set, values.column_rename]);

  const addExtraHeader = useCallback(() => {
    set('extra_headers', [
      ...(values.extra_headers ?? []),
      { key: '', value: '' },
    ]);
  }, [set, values.extra_headers]);

  // ── Save ───────────────────────────────────────────────────────────

  const handleSave = useCallback(async () => {
    setSaving(true);
    const payload = formValuesToPayload(values);
    const endpoint = isEditing ? `/api/v1/etl/${job!.id}` : '/api/v1/etl/';
    const method = isEditing ? 'put' : 'post';

    try {
      await SupersetClient[method]({ endpoint, jsonPayload: payload });
      addSuccessToast(
        isEditing
          ? t('ETL Job "%s" updated', values.name)
          : t('ETL Job "%s" created', values.name),
      );
      onSave();
    } catch (err: any) {
      const msg = err?.data?.message || t('Failed to save ETL job');
      addDangerToast(String(msg));
    } finally {
      setSaving(false);
    }
  }, [values, isEditing, job, addSuccessToast, addDangerToast, onSave]);

  // ── Step 1: Basic Info ─────────────────────────────────────────────

  const step1 = (
    <Form layout="vertical">
      <Form.Item label={t('Name')} required>
        <Input
          value={values.name}
          onChange={e => set('name', e.target.value)}
          placeholder={t('My ETL job')}
        />
      </Form.Item>

      <Form.Item label={t('Description')}>
        <Input.TextArea
          value={values.description}
          onChange={e => set('description', e.target.value)}
          rows={2}
        />
      </Form.Item>

      <Form.Item label={t('Active')}>
        <Switch
          checked={values.active}
          onChange={v => set('active', v)}
        />
      </Form.Item>

      <Form.Item label={t('Schedule type')} required>
        <Select
          value={values.schedule_type}
          onChange={v => set('schedule_type', v as EtlScheduleType)}
          options={[
            { label: t('Cron (recurring)'), value: 'cron' },
            { label: t('One-time'), value: 'onetime' },
          ]}
        />
      </Form.Item>

      {values.schedule_type === 'cron' ? (
        <Form.Item
          label={t('Cron expression')}
          required
          help={t('Example: "0 * * * *" runs every hour')}
        >
          <Input
            value={values.crontab}
            onChange={e => set('crontab', e.target.value)}
            placeholder="0 * * * *"
          />
        </Form.Item>
      ) : (
        <Form.Item label={t('Run at (UTC)')} required>
          <Input
            type="datetime-local"
            value={values.run_at}
            onChange={e => set('run_at', e.target.value)}
          />
        </Form.Item>
      )}

      <Form.Item label={t('Timezone')}>
        <Input
          value={values.timezone}
          onChange={e => set('timezone', e.target.value)}
          placeholder="Asia/Taipei"
        />
      </Form.Item>
    </Form>
  );

  // ── Step 2: Sources ────────────────────────────────────────────────

  const hasSmbSource = values.sources.some(s =>
    s.url.toLowerCase().startsWith('smb://'),
  );

  const step2 = (
    <div>
      <p>{t('Add one or more source URLs. Files will be downloaded and concatenated.')}</p>
      <p style={{ fontSize: 12, color: '#888' }}>
        {t('Supported schemes: http://, https://, smb://')}
      </p>

      {/* HTTP Authentication */}
      <Form layout="vertical">
        <Form.Item
          label={t('Bearer Token (HTTP/HTTPS, optional)')}
          help={t('Applies to all HTTP/HTTPS source URLs as the Authorization header')}
        >
          <Input.Password
            value={values.bearer_token}
            onChange={e => set('bearer_token', e.target.value)}
            placeholder={t('Your token here')}
          />
        </Form.Item>

        {(values.extra_headers ?? []).map((h, idx) => (
          // eslint-disable-next-line react/no-array-index-key
          <RowFlex key={idx}>
            <Form.Item label={idx === 0 ? t('Header name') : ''} style={{ flex: 1 }}>
              <Input
                value={h.key}
                onChange={e => {
                  const updated = [...(values.extra_headers ?? [])];
                  updated[idx] = { ...h, key: e.target.value };
                  set('extra_headers', updated);
                }}
                placeholder="X-Custom-Header"
              />
            </Form.Item>
            <Form.Item label={idx === 0 ? t('Value') : ''} style={{ flex: 2 }}>
              <Input
                value={h.value}
                onChange={e => {
                  const updated = [...(values.extra_headers ?? [])];
                  updated[idx] = { ...h, value: e.target.value };
                  set('extra_headers', updated);
                }}
              />
            </Form.Item>
            <Tooltip title={t('Remove header')}>
              <Button
                buttonStyle="link"
                onClick={() => {
                  set(
                    'extra_headers',
                    (values.extra_headers ?? []).filter((_, i) => i !== idx),
                  );
                }}
              >
                <Icons.Trash />
              </Button>
            </Tooltip>
          </RowFlex>
        ))}
        <AddButton buttonStyle="tertiary" onClick={addExtraHeader}>
          <Icons.PlusSmall />
          {t('Add HTTP header')}
        </AddButton>
      </Form>

      {/* SMB Credentials — shown only when at least one source is smb:// */}
      {hasSmbSource && (
        <>
          <hr style={{ margin: '16px 0' }} />
          <p>
            <strong>{t('SMB Credentials')}</strong>
            {' '}
            <span style={{ fontSize: 12, color: '#888' }}>
              {t('(shared across all smb:// sources in this job)')}
            </span>
          </p>
          <Form layout="vertical">
            <RowFlex>
              <Form.Item label={t('Username')} style={{ flex: 1 }}>
                <Input
                  value={values.smb_username}
                  onChange={e => set('smb_username', e.target.value)}
                  placeholder={t('domain\\user or user')}
                />
              </Form.Item>
              <Form.Item label={t('Password')} style={{ flex: 1 }}>
                <Input.Password
                  value={values.smb_password}
                  onChange={e => set('smb_password', e.target.value)}
                />
              </Form.Item>
            </RowFlex>
            <RowFlex>
              <Form.Item
                label={t('Domain / Workgroup (optional)')}
                style={{ flex: 1 }}
              >
                <Input
                  value={values.smb_domain}
                  onChange={e => set('smb_domain', e.target.value)}
                  placeholder="WORKGROUP"
                />
              </Form.Item>
              <Form.Item
                label={t('Port (default 445)')}
                style={{ flex: 1 }}
              >
                <Input
                  value={values.smb_port}
                  onChange={e => set('smb_port', e.target.value)}
                  placeholder="445"
                  type="number"
                />
              </Form.Item>
            </RowFlex>
          </Form>
        </>
      )}

      <hr style={{ margin: '16px 0' }} />

      {values.sources.length === 0 && (
        <EmptySourcesHint>{t('No sources added yet.')}</EmptySourcesHint>
      )}

      {values.sources.map((src, idx) => (
        // eslint-disable-next-line react/no-array-index-key
        <SourceCard key={idx}>
          <RowFlex style={{ justifyContent: 'space-between' }}>
            <strong>{t('Source %s', idx + 1)}</strong>
            {values.sources.length > 1 && (
              <Tooltip title={t('Remove source')}>
                <Button buttonStyle="link" onClick={() => removeSource(idx)}>
                  <Icons.Trash />
                </Button>
              </Tooltip>
            )}
          </RowFlex>

          <Form layout="vertical">
            <Form.Item label={t('URL')} required>
              <Input
                value={src.url}
                onChange={e => setSource(idx, 'url', e.target.value)}
                placeholder="https://example.com/data.csv"
              />
            </Form.Item>

            <RowFlex>
              <Form.Item label={t('Delimiter (CSV/TSV)')} style={{ flex: 1 }}>
                <Input
                  value={src.delimiter ?? ''}
                  onChange={e =>
                    setSource(idx, 'delimiter', e.target.value || null)
                  }
                  placeholder=","
                />
              </Form.Item>
              <Form.Item label={t('Sheet name (Excel)')} style={{ flex: 1 }}>
                <Input
                  value={src.sheet_name ?? ''}
                  onChange={e =>
                    setSource(idx, 'sheet_name', e.target.value || null)
                  }
                  placeholder={t('Sheet1')}
                />
              </Form.Item>
              <Form.Item label={t('Encoding')} style={{ flex: 1 }}>
                <Input
                  value={src.encoding ?? ''}
                  onChange={e =>
                    setSource(idx, 'encoding', e.target.value || null)
                  }
                  placeholder="utf-8"
                />
              </Form.Item>
            </RowFlex>
          </Form>
        </SourceCard>
      ))}

      <AddButton buttonStyle="tertiary" onClick={addSource}>
        <Icons.PlusSmall />
        {t('Add source URL')}
      </AddButton>
    </div>
  );

  // ── Step 3: Target & Column settings ──────────────────────────────

  const step3 = (
    <Form layout="vertical">
      {/* Target database */}
      <Form.Item label={t('Target database')} required>
        <Select
          value={values.database_id}
          onChange={v => set('database_id', v as number)}
          options={databases.map(db => ({
            label: db.database_name,
            value: db.id,
          }))}
          showSearch
          filterOption={(input, option) =>
            String(option?.label ?? '')
              .toLowerCase()
              .includes(input.toLowerCase())
          }
        />
      </Form.Item>

      <RowFlex>
        <Form.Item label={t('Schema')} style={{ flex: 1 }}>
          <Input
            value={values.target_schema}
            onChange={e => set('target_schema', e.target.value)}
            placeholder={t('optional')}
          />
        </Form.Item>
        <Form.Item label={t('Table name')} required style={{ flex: 2 }}>
          <Input
            value={values.target_table}
            onChange={e => set('target_table', e.target.value)}
            placeholder="my_table"
          />
        </Form.Item>
      </RowFlex>

      <RowFlex>
        <Form.Item label={t('File type')} style={{ flex: 1 }}>
          <Select
            value={values.file_type}
            onChange={v => set('file_type', v as EtlFileType)}
            options={[
              { label: t('Auto-detect'), value: 'auto' },
              { label: 'CSV', value: 'csv' },
              { label: 'TSV', value: 'tsv' },
              { label: 'Excel', value: 'excel' },
            ]}
          />
        </Form.Item>
        <Form.Item label={t('If table exists')} style={{ flex: 1 }}>
          <Select
            value={values.if_exists}
            onChange={v => set('if_exists', v as EtlIfExists)}
            options={[
              { label: t('Fail'), value: 'fail' },
              { label: t('Append'), value: 'append' },
              { label: t('Replace'), value: 'replace' },
            ]}
          />
        </Form.Item>
        <Form.Item label={t('Write index')} style={{ flex: 1 }}>
          <Switch
            checked={values.dataframe_index}
            onChange={v => set('dataframe_index', v)}
          />
        </Form.Item>
      </RowFlex>

      {/* Column filtering */}
      <Form.Item
        label={t('Column filter (keep only listed columns)')}
        help={t('Leave empty to keep all columns')}
      >
        {(values.columns_read ?? []).map((col, idx) => (
          // eslint-disable-next-line react/no-array-index-key
          <RowFlex key={idx} style={{ marginBottom: 4 }}>
            <Input
              value={col}
              onChange={e => {
                const updated = [...(values.columns_read ?? [])];
                updated[idx] = e.target.value;
                set('columns_read', updated);
              }}
              placeholder={t('column_name')}
            />
            <Tooltip title={t('Remove')}>
              <Button
                buttonStyle="link"
                onClick={() =>
                  set(
                    'columns_read',
                    (values.columns_read ?? []).filter((_, i) => i !== idx),
                  )
                }
              >
                <Icons.Trash />
              </Button>
            </Tooltip>
          </RowFlex>
        ))}
        <AddButton buttonStyle="tertiary" onClick={addColumnRead}>
          <Icons.PlusSmall />
          {t('Add column')}
        </AddButton>
      </Form.Item>

      {/* Column type casting */}
      <Form.Item label={t('Column type overrides')}>
        {(values.column_data_types ?? []).map((entry, idx) => (
          // eslint-disable-next-line react/no-array-index-key
          <RowFlex key={idx} style={{ marginBottom: 4 }}>
            <Input
              value={entry.name}
              onChange={e => {
                const updated = [...(values.column_data_types ?? [])];
                updated[idx] = { ...entry, name: e.target.value };
                set('column_data_types', updated);
              }}
              placeholder={t('column_name')}
              style={{ flex: 1 }}
            />
            <Select
              value={entry.dtype}
              onChange={v => {
                const updated = [...(values.column_data_types ?? [])];
                updated[idx] = { ...entry, dtype: v as string };
                set('column_data_types', updated);
              }}
              options={PANDAS_DTYPES}
              style={{ flex: 1 }}
            />
            <Tooltip title={t('Remove')}>
              <Button
                buttonStyle="link"
                onClick={() =>
                  set(
                    'column_data_types',
                    (values.column_data_types ?? []).filter(
                      (_, i) => i !== idx,
                    ),
                  )
                }
              >
                <Icons.Trash />
              </Button>
            </Tooltip>
          </RowFlex>
        ))}
        <AddButton buttonStyle="tertiary" onClick={addColumnType}>
          <Icons.PlusSmall />
          {t('Add type override')}
        </AddButton>
      </Form.Item>

      {/* Column renaming */}
      <Form.Item label={t('Column renaming')}>
        {(values.column_rename ?? []).map((entry, idx) => (
          // eslint-disable-next-line react/no-array-index-key
          <RowFlex key={idx} style={{ marginBottom: 4 }}>
            <Input
              value={entry.old_name}
              onChange={e => {
                const updated = [...(values.column_rename ?? [])];
                updated[idx] = { ...entry, old_name: e.target.value };
                set('column_rename', updated);
              }}
              placeholder={t('Original name')}
              style={{ flex: 1 }}
            />
            <span>→</span>
            <Input
              value={entry.new_name}
              onChange={e => {
                const updated = [...(values.column_rename ?? [])];
                updated[idx] = { ...entry, new_name: e.target.value };
                set('column_rename', updated);
              }}
              placeholder={t('New name')}
              style={{ flex: 1 }}
            />
            <Tooltip title={t('Remove')}>
              <Button
                buttonStyle="link"
                onClick={() =>
                  set(
                    'column_rename',
                    (values.column_rename ?? []).filter((_, i) => i !== idx),
                  )
                }
              >
                <Icons.Trash />
              </Button>
            </Tooltip>
          </RowFlex>
        ))}
        <AddButton buttonStyle="tertiary" onClick={addColumnRename}>
          <Icons.PlusSmall />
          {t('Add rename rule')}
        </AddButton>
      </Form.Item>

      {/* Operational */}
      <RowFlex>
        <Form.Item
          label={t('Log retention (days)')}
          style={{ flex: 1 }}
        >
          <InputNumber
            min={1}
            value={values.log_retention}
            onChange={v => set('log_retention', v ?? 90)}
            style={{ width: '100%' }}
          />
        </Form.Item>
        <Form.Item
          label={t('Timeout (seconds)')}
          style={{ flex: 1 }}
        >
          <InputNumber
            min={60}
            value={values.working_timeout}
            onChange={v => set('working_timeout', v ?? 3600)}
            style={{ width: '100%' }}
          />
        </Form.Item>
      </RowFlex>
    </Form>
  );

  // ── Step configuration ─────────────────────────────────────────────

  const steps = [
    { title: t('Basic info'), content: step1 },
    { title: t('Sources'), content: step2 },
    { title: t('Target & Columns'), content: step3 },
  ];

  // ── Footer buttons ─────────────────────────────────────────────────

  const footer = (
    <RowFlex style={{ justifyContent: 'flex-end' }}>
      <Button onClick={onHide}>{t('Cancel')}</Button>
      {step > 0 && (
        <Button onClick={() => setStep(s => s - 1)}>{t('Previous')}</Button>
      )}
      {step < steps.length - 1 ? (
        <Button buttonStyle="primary" onClick={() => setStep(s => s + 1)}>
          {t('Next')}
        </Button>
      ) : (
        <Button buttonStyle="primary" loading={saving} onClick={handleSave}>
          {isEditing ? t('Update') : t('Create')}
        </Button>
      )}
    </RowFlex>
  );

  // ── Render ─────────────────────────────────────────────────────────

  return (
    <Modal
      title={isEditing ? t('Edit ETL Job') : t('New ETL Job')}
      footer={footer}
      onHide={onHide}
      show
      width="760px"
    >
      <Steps current={step} size="small" style={{ marginBottom: 24 }}>
        {steps.map(s => (
          <Steps.Step key={s.title} title={s.title} />
        ))}
      </Steps>

      {steps[step].content}
    </Modal>
  );
}

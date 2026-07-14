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

import { useCallback, useEffect, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { SupersetClient } from '@superset-ui/core';
import { Badge, Modal, Pagination, Tooltip } from '@superset-ui/core/components';
import { css, styled } from '@apache-superset/core/theme';
import type { EtlJob, EtlJobLog, EtlState } from './types';

// ── State badge ───────────────────────────────────────────────────────────

const STATE_STATUS: Record<string, 'success' | 'processing' | 'error' | 'default'> = {
  success: 'success',
  working: 'processing',
  error: 'error',
  pending: 'default',
};

// ── Styled components ─────────────────────────────────────────────────────

const LogRow = styled.div`
  ${({ theme }) => css`
    display: flex;
    flex-direction: column;
    border-bottom: 1px solid ${theme.colorBorderSecondary};
    padding: ${theme.gridUnit * 2}px 0;
    gap: ${theme.gridUnit}px;

    &:last-child {
      border-bottom: none;
    }
  `}
`;

const LogMeta = styled.div`
  ${({ theme }) => css`
    display: flex;
    gap: ${theme.gridUnit * 3}px;
    align-items: center;
    font-size: ${theme.fontSizeSM}px;
    color: ${theme.colorTextSecondary};
  `}
`;

const ErrorBlock = styled.pre`
  ${({ theme }) => css`
    background: ${theme.colorBgLayout};
    border: 1px solid ${theme.colorBorderSecondary};
    border-radius: ${theme.borderRadius}px;
    padding: ${theme.gridUnit * 2}px;
    font-size: ${theme.fontSizeSM}px;
    color: ${theme.colorError};
    white-space: pre-wrap;
    word-break: break-all;
    margin: 0;
  `}
`;

const EmptyMessage = styled.p`
  ${({ theme }) => css`
    color: ${theme.colorTextSecondary};
    font-style: italic;
    text-align: center;
    padding: ${theme.gridUnit * 4}px 0;
  `}
`;

// ── Props ─────────────────────────────────────────────────────────────────

interface EtlJobLogModalProps {
  job: EtlJob;
  onHide: () => void;
  addDangerToast: (msg: string) => void;
}

// ── Component ─────────────────────────────────────────────────────────────

export default function EtlJobLogModal({
  job,
  onHide,
  addDangerToast,
}: EtlJobLogModalProps) {
  const [logs, setLogs] = useState<EtlJobLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(false);
  const pageSize = 20;

  const fetchLogs = useCallback(
    (p: number) => {
      setLoading(true);
      SupersetClient.get({
        endpoint: `/api/v1/etl/${job.id}/logs/?page=${p}&page_size=${pageSize}`,
      })
        .then(({ json }) => {
          const data = json as { count: number; result: EtlJobLog[] };
          setLogs(data.result);
          setTotal(data.count);
        })
        .catch(() => addDangerToast(t('Failed to load logs')))
        .finally(() => setLoading(false));
    },
    [job.id, addDangerToast],
  );

  useEffect(() => {
    fetchLogs(0);
  }, [fetchLogs]);

  const handlePageChange = useCallback(
    (newPage: number) => {
      const p = newPage - 1;
      setPage(p);
      fetchLogs(p);
    },
    [fetchLogs],
  );

  const duration = (log: EtlJobLog): string => {
    if (!log.end_dttm) return t('running…');
    const ms =
      new Date(log.end_dttm).getTime() - new Date(log.start_dttm).getTime();
    const secs = Math.round(ms / 1000);
    if (secs < 60) return t('%ss', secs);
    return t('%sm %ss', Math.floor(secs / 60), secs % 60);
  };

  return (
    <Modal
      title={t('Execution Logs — %s', job.name)}
      onHide={onHide}
      show
      width="760px"
      footer={
        <Pagination
          current={page + 1}
          pageSize={pageSize}
          total={total}
          onChange={handlePageChange}
          showTotal={t_total => t('%s logs total', t_total)}
          size="small"
        />
      }
    >
      {loading && <p>{t('Loading…')}</p>}

      {!loading && logs.length === 0 && (
        <EmptyMessage>{t('No execution logs yet for this job.')}</EmptyMessage>
      )}

      {logs.map(log => (
        <LogRow key={log.id}>
          <LogMeta>
            <Badge
              status={STATE_STATUS[log.state] ?? 'default'}
              text={log.state.charAt(0).toUpperCase() + log.state.slice(1)}
            />
            <span>
              {t('Started: %s', new Date(log.start_dttm).toLocaleString())}
            </span>
            <span>{t('Duration: %s', duration(log))}</span>
            {log.rows_imported != null && (
              <span>{t('%s rows imported', log.rows_imported.toLocaleString())}</span>
            )}
            {log.celery_task_id && (
              <Tooltip title={log.celery_task_id}>
                <span
                  style={{
                    fontFamily: 'monospace',
                    maxWidth: 120,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    display: 'inline-block',
                  }}
                >
                  {log.celery_task_id}
                </span>
              </Tooltip>
            )}
          </LogMeta>

          {log.error_message && (
            <ErrorBlock>{log.error_message}</ErrorBlock>
          )}
        </LogRow>
      ))}
    </Modal>
  );
}

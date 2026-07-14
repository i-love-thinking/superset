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

import { useCallback, useMemo, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import { SupersetClient } from '@superset-ui/core';
import { css, styled } from '@apache-superset/core/theme';
import {
  Badge,
  DeleteModal,
  Tooltip,
} from '@superset-ui/core/components';
import { Icons } from '@superset-ui/core/components/Icons';
import {
  ListView,
  ListViewFilterOperator as FilterOperator,
  ListViewActionsBar,
  type ListViewProps,
  type ListViewFilters,
} from 'src/components';
import SubMenu, { SubMenuProps } from 'src/features/home/SubMenu';
import withToasts from 'src/components/MessageToasts/withToasts';
import { useListViewResource } from 'src/views/CRUD/hooks';
import { DATETIME_WITH_TIME_ZONE } from 'src/constants';
import EtlJobModal from './EtlJobModal';
import EtlJobLogModal from './EtlJobLogModal';
import type { EtlJob, EtlJobListProps, EtlState } from './types';

const PAGE_SIZE = 25;

// ── State badge colours ───────────────────────────────────────────────────
const STATE_BADGE_STATUS: Record<string, 'success' | 'processing' | 'error' | 'default'> = {
  success: 'success',
  working: 'processing',
  error: 'error',
  pending: 'default',
};

const StateBadge = ({ state }: { state: EtlState | null | undefined }) => {
  if (!state) return <span>—</span>;
  return (
    <Badge
      status={STATE_BADGE_STATUS[state] ?? 'default'}
      text={state.charAt(0).toUpperCase() + state.slice(1)}
    />
  );
};

// ── Styled containers ─────────────────────────────────────────────────────
const IconContainer = styled.span`
  ${({ theme }) => css`
    display: inline-flex;
    gap: ${theme.gridUnit}px;
  `}
`;

// ── Component ─────────────────────────────────────────────────────────────

function EtlJobList({ addDangerToast, addSuccessToast }: EtlJobListProps) {
  const [jobModalOpen, setJobModalOpen] = useState(false);
  const [logModalOpen, setLogModalOpen] = useState(false);
  const [currentJob, setCurrentJob] = useState<EtlJob | null>(null);
  const [logJob, setLogJob] = useState<EtlJob | null>(null);
  const [jobToDelete, setJobToDelete] = useState<EtlJob | null>(null);

  const {
    state: { loading, resourceCount, resourceCollection },
    hasPerm,
    fetchData,
    refreshData,
  } = useListViewResource<EtlJob>('etl', t('ETL Job'), addDangerToast);

  // ── Handlers ───────────────────────────────────────────────────────

  const handleCreate = useCallback(() => {
    setCurrentJob(null);
    setJobModalOpen(true);
  }, []);

  const handleEdit = useCallback((job: EtlJob) => {
    setCurrentJob(job);
    setJobModalOpen(true);
  }, []);

  const handleViewLogs = useCallback((job: EtlJob) => {
    setLogJob(job);
    setLogModalOpen(true);
  }, []);

  const handleDelete = useCallback(
    (job: EtlJob) => {
      SupersetClient.delete({ endpoint: `/api/v1/etl/${job.id}` })
        .then(() => {
          addSuccessToast(t('ETL Job "%s" deleted', job.name));
          refreshData();
        })
        .catch(() => {
          addDangerToast(t('Failed to delete ETL Job "%s"', job.name));
        })
        .finally(() => setJobToDelete(null));
    },
    [addSuccessToast, addDangerToast, refreshData],
  );

  const handleExecute = useCallback(
    (job: EtlJob) => {
      SupersetClient.post({ endpoint: `/api/v1/etl/${job.id}/execute/` })
        .then(() => {
          addSuccessToast(t('ETL Job "%s" queued for execution', job.name));
          refreshData();
        })
        .catch(() => {
          addDangerToast(t('Failed to trigger ETL Job "%s"', job.name));
        });
    },
    [addSuccessToast, addDangerToast, refreshData],
  );

  const handleModalSave = useCallback(() => {
    refreshData();
    setJobModalOpen(false);
  }, [refreshData]);

  // ── Table columns ──────────────────────────────────────────────────

  const columns = useMemo(
    () => [
      {
        accessor: 'name',
        Header: t('Name'),
        Cell: ({ row: { original } }: { row: { original: EtlJob } }) => (
          <a
            role="button"
            tabIndex={0}
            onClick={() => handleEdit(original)}
            onKeyDown={e => e.key === 'Enter' && handleEdit(original)}
            style={{ cursor: 'pointer' }}
          >
            {original.name}
          </a>
        ),
      },
      {
        accessor: 'active',
        Header: t('Active'),
        Cell: ({ value }: { value: boolean }) => (
          <Badge status={value ? 'success' : 'default'} text={value ? t('Yes') : t('No')} />
        ),
        size: 'xs',
      },
      {
        accessor: 'database.database_name',
        Header: t('Database'),
      },
      {
        accessor: 'target_table',
        Header: t('Target Table'),
        Cell: ({ row: { original } }: { row: { original: EtlJob } }) =>
          original.target_schema
            ? `${original.target_schema}.${original.target_table}`
            : original.target_table,
      },
      {
        accessor: 'schedule_type',
        Header: t('Schedule'),
        Cell: ({ row: { original } }: { row: { original: EtlJob } }) =>
          original.schedule_type === 'cron'
            ? original.crontab || '—'
            : original.run_at
            ? new Date(original.run_at).toLocaleString()
            : '—',
      },
      {
        accessor: 'last_run_dttm',
        Header: t('Last Run'),
        Cell: ({ value }: { value: string | null }) =>
          value ? new Date(value).toLocaleString() : '—',
      },
      {
        accessor: 'last_run_state',
        Header: t('Status'),
        Cell: ({ value }: { value: EtlState | null }) => (
          <StateBadge state={value} />
        ),
        size: 'sm',
      },
      {
        accessor: 'sources',
        Header: t('Sources'),
        Cell: ({ value }: { value: EtlJob['sources'] }) => value?.length ?? 0,
        disableSortBy: true,
        size: 'xs',
      },
    ],
    [handleEdit],
  );

  // ── Row actions ────────────────────────────────────────────────────

  const actions = useMemo(
    () => [
      {
        label: t('Run now'),
        tooltip: t('Trigger immediate execution'),
        icon: 'Play' as const,
        onClick: handleExecute,
        show: () => hasPerm('can_write'),
      },
      {
        label: t('Logs'),
        tooltip: t('View execution logs'),
        icon: 'List' as const,
        onClick: handleViewLogs,
        show: () => hasPerm('can_read'),
      },
      {
        label: t('Edit'),
        tooltip: t('Edit ETL job'),
        icon: 'Edit' as const,
        onClick: handleEdit,
        show: () => hasPerm('can_write'),
      },
      {
        label: t('Delete'),
        tooltip: t('Delete ETL job'),
        icon: 'Trash' as const,
        onClick: (job: EtlJob) => setJobToDelete(job),
        show: () => hasPerm('can_write'),
      },
    ],
    [handleExecute, handleViewLogs, handleEdit, hasPerm],
  );

  // ── SubMenu buttons ────────────────────────────────────────────────

  const subMenuButtons: SubMenuProps['buttons'] = [];
  if (hasPerm('can_write')) {
    subMenuButtons.push({
      name: (
        <IconContainer>
          <Icons.PlusSmall />
          {t('ETL Job')}
        </IconContainer>
      ),
      buttonStyle: 'primary',
      onClick: handleCreate,
    });
  }

  // ── Filters ────────────────────────────────────────────────────────

  const filters: ListViewFilters = [
    {
      Header: t('Name'),
      key: 'name',
      id: 'name',
      input: 'search',
      operator: FilterOperator.Contains,
    },
    {
      Header: t('Active'),
      key: 'active',
      id: 'active',
      input: 'select',
      operator: FilterOperator.Equals,
      selects: [
        { label: t('Yes'), value: true },
        { label: t('No'), value: false },
      ],
    },
    {
      Header: t('Status'),
      key: 'last_run_state',
      id: 'last_run_state',
      input: 'select',
      operator: FilterOperator.Equals,
      selects: [
        { label: t('Success'), value: 'success' },
        { label: t('Working'), value: 'working' },
        { label: t('Error'), value: 'error' },
        { label: t('Pending'), value: 'pending' },
      ],
    },
  ];

  // ── Render ─────────────────────────────────────────────────────────

  return (
    <>
      <SubMenu name={t('ETL Jobs')} buttons={subMenuButtons} />

      <ListView<EtlJob>
        className="etl-job-list-view"
        columns={columns}
        count={resourceCount}
        data={resourceCollection}
        fetchData={fetchData}
        filters={filters}
        initialSort={[{ id: 'changed_on', desc: true }]}
        loading={loading}
        pageSize={PAGE_SIZE}
        renderRowActionButtons={row => (
          <ListViewActionsBar
            row={row}
            actions={actions}
          />
        )}
      />

      {jobModalOpen && (
        <EtlJobModal
          job={currentJob}
          onHide={() => setJobModalOpen(false)}
          onSave={handleModalSave}
          addDangerToast={addDangerToast}
          addSuccessToast={addSuccessToast}
        />
      )}

      {logModalOpen && logJob && (
        <EtlJobLogModal
          job={logJob}
          onHide={() => setLogModalOpen(false)}
          addDangerToast={addDangerToast}
        />
      )}

      {jobToDelete && (
        <DeleteModal
          description={t(
            'This action will permanently delete "%s". Are you sure?',
            jobToDelete.name,
          )}
          onConfirm={() => handleDelete(jobToDelete)}
          onHide={() => setJobToDelete(null)}
          open
          title={t('Delete ETL Job')}
        />
      )}
    </>
  );
}

export default withToasts(EtlJobList);

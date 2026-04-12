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

import { useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { t } from '@apache-superset/core/translation';
import {
  BinaryQueryObjectFilterClause,
  BaseFormData,
  Column,
  QueryData,
  ensureIsArray,
  isDefined,
  ContextMenuFilters,
  AdhocFilter,
} from '@superset-ui/core';
import { Alert } from '@apache-superset/core/components';
import { css, useTheme } from '@apache-superset/core/theme';
import { useDispatch, useSelector } from 'react-redux';
import { Link } from 'react-router-dom';
import {
  Button,
  Modal,
  Loading,
  Breadcrumb,
  Flex,
} from '@superset-ui/core/components';
import { RootState } from 'src/dashboard/types';
import { DashboardPageIdContext } from 'src/dashboard/containers/DashboardPage';
import { postFormData } from 'src/explore/exploreUtils/formData';
import { simpleFilterToAdhoc } from 'src/utils/simpleFilterToAdhoc';
import { useDatasetMetadataBar } from 'src/features/datasets/metadataBar/useDatasetMetadataBar';
import { useToasts } from 'src/components/MessageToasts/withToasts';
import { logEvent } from 'src/logger/actions';
import {
  LOG_ACTIONS_DRILL_BY_BREADCRUMB_CLICKED,
  LOG_ACTIONS_DRILL_BY_EDIT_CHART,
  LOG_ACTIONS_DRILL_BY_MODAL_OPENED,
  LOG_ACTIONS_FURTHER_DRILL_BY,
} from 'src/logger/LogUtils';
import { findPermission } from 'src/utils/findPermission';
import { getQuerySettings } from 'src/explore/exploreUtils';
import { isEmbedded } from 'src/dashboard/util/isEmbedded';
import { Dataset, DrillByType } from '../types';
import DrillByChart from './DrillByChart';
import { ContextMenuItem } from '../ChartContextMenu/ChartContextMenu';
import { useContextMenu } from '../ChartContextMenu/useContextMenu';
import { getChartDataRequest, handleChartDataResponse } from '../chartAction';
import { useDisplayModeToggle } from './useDisplayModeToggle';
import { useResultsTableView } from './useResultsTableView';

const DEFAULT_ADHOC_FILTER_FIELD_NAME = 'adhoc_filters';

interface ModalFooterProps {
  closeModal?: () => void;
  formData: BaseFormData;
}

interface HierarchicalDrillByBreadcrumb {
  columns: Column[];
  filters?: BinaryQueryObjectFilterClause[];
}

const ModalFooter = ({ formData, closeModal }: ModalFooterProps) => {
  const dispatch = useDispatch();
  const { addDangerToast } = useToasts();
  const theme = useTheme();
  const dashboardPageId = useContext(DashboardPageIdContext);
  const { roles } = useSelector<RootState, RootState['user']>(
    ({ user }) => user,
  );
  const canExplore = findPermission('can_explore', 'Superset', roles);

  return (
    <>
      {!isEmbedded() && canExplore && (
        <Button
          buttonStyle="tertiary"
          buttonSize="small"
          onClick={async () => {
            try {
              const key = await postFormData(
                Number(formData.datasource?.split('__')[0]),
                formData.datasource?.split('__')[1] || 'table',
                formData,
                formData.slice_id,
              );
              const url = `/explore/?form_data_key=${key}&dashboard_page_id=${dashboardPageId}`;
              dispatch(
                logEvent(LOG_ACTIONS_DRILL_BY_EDIT_CHART, {
                  slice_id: formData.slice_id,
                }),
              );
              window.open(url, '_blank');
            } catch {
              addDangerToast(
                t('An error occurred while opening the chart editor'),
              );
            }
          }}
          css={css`
            margin-right: auto;
          `}
        >
          {t('Edit chart')}
        </Button>
      )}

      <Button
        buttonStyle="primary"
        buttonSize="small"
        onClick={closeModal}
        data-test="close-hierarchical-drill-by-modal"
        css={css`
          margin-left: ${theme.sizeUnit * 2}px;
        `}
      >
        {t('Close')}
      </Button>
    </>
  );
};

export interface HierarchicalDrillByModalProps {
  column?: Column;
  dataset: Dataset;
  drillByConfig: Required<ContextMenuFilters>['hierarchicalDrillBy'];
  formData: BaseFormData & { [key: string]: any };
  onHideModal: () => void;
  canDownload: boolean;
}

type DrillByConfig = ContextMenuFilters['hierarchicalDrillBy'] & {
  column?: Column;
};

export default function HierarchicalDrillByModal({
  column,
  dataset,
  drillByConfig,
  formData,
  onHideModal,
  canDownload,
}: HierarchicalDrillByModalProps) {
  const dispatch = useDispatch();
  const theme = useTheme();
  const { addDangerToast } = useToasts();
  const [isChartDataLoading, setIsChartDataLoading] = useState(true);

  // Accumulated drill configs — each entry adds one column to the hierarchy
  const [drillConfigs, setDrillConfigs] = useState<DrillByConfig[]>([
    { ...drillByConfig, column },
  ]);

  useEffect(() => {
    dispatch(
      logEvent(LOG_ACTIONS_DRILL_BY_MODAL_OPENED, {
        slice_id: formData.slice_id,
      }),
    );
  }, [dispatch, formData.slice_id]);

  const { groupbyFieldName = drillByConfig.groupbyFieldName } =
    drillConfigs[drillConfigs.length - 1] ?? {};

  // Original groupby columns from the initial formData
  const originalGroupbyColumns = useMemo(
    () =>
      ensureIsArray(formData[groupbyFieldName])
        .map((colName: string) =>
          dataset.columns?.find(col => col.column_name === colName),
        )
        .filter(isDefined),
    [dataset.columns, formData, groupbyFieldName],
  );

  const { displayModeToggle, drillByDisplayMode } = useDisplayModeToggle();
  const [chartDataResult, setChartDataResult] = useState<QueryData[]>();

  const resultsTable = useResultsTableView(
    chartDataResult,
    formData.datasource,
    canDownload,
  );

  // All columns accumulated so far (drill columns selected in the modal)
  const drillColumns = useMemo(
    () => drillConfigs.map(c => c.column).filter(isDefined) as Column[],
    [drillConfigs],
  );

  // All columns that should be excluded from further drill selection
  const usedGroupbyColumns = useMemo(
    () => [...originalGroupbyColumns, ...drillColumns],
    [originalGroupbyColumns, drillColumns],
  );

  // Breadcrumb data: starts with original groupby, grows with each drill
  const [breadcrumbsData, setBreadcrumbsData] = useState<
    HierarchicalDrillByBreadcrumb[]
  >([
    { columns: originalGroupbyColumns, filters: drillByConfig.filters },
    { columns: column ? [column] : [] },
  ]);

  /**
   * Build drilledFormData for hierarchical display:
   * - x_axis = last selected drill column (leaf)
   * - groupby = original groupby + all previous drill columns (parent levels)
   * - _hierarchicalDrillBy = true (signals transformProps to render hierarchical axes)
   * - adhoc_filters accumulate from all drill steps
   */
  const drilledFormData = useMemo(() => {
    if (drillColumns.length === 0) {
      return formData;
    }

    const leafColumn = drillColumns[drillColumns.length - 1];
    // Parent levels: original groupby + intermediate drill columns (all except leaf)
    const parentColumns = [
      ...originalGroupbyColumns.map((c: Column) => c.column_name),
      ...drillColumns.slice(0, -1).map(c => c.column_name),
    ];

    // Accumulate adhoc filters from all drill configs
    const accumulatedFilters: AdhocFilter[] = drillConfigs
      .flatMap(config => ensureIsArray(config?.filters))
      .map(filter => simpleFilterToAdhoc(filter));

    const adhocFilterFieldName =
      drillByConfig.adhocFilterFieldName || DEFAULT_ADHOC_FILTER_FIELD_NAME;

    return {
      ...formData,
      x_axis: leafColumn.column_name,
      [groupbyFieldName]: parentColumns,
      [adhocFilterFieldName]: [
        ...ensureIsArray(formData[adhocFilterFieldName]),
        ...accumulatedFilters,
      ],
      _hierarchicalDrillBy: true,
      slice_id: 0,
      slice_name: undefined,
      dashboards: undefined,
    };
  }, [
    drillColumns,
    drillConfigs,
    drillByConfig.adhocFilterFieldName,
    formData,
    groupbyFieldName,
    originalGroupbyColumns,
  ]);

  const onBreadcrumbClick = useCallback(
    (index: number) => {
      dispatch(
        logEvent(LOG_ACTIONS_DRILL_BY_BREADCRUMB_CLICKED, {
          slice_id: formData.slice_id,
        }),
      );
      setDrillConfigs(prev => prev.slice(0, index));
      setBreadcrumbsData(prev => {
        const updated = prev.slice(0, index + 1);
        delete updated[updated.length - 1].filters;
        return updated;
      });
    },
    [dispatch, formData.slice_id],
  );

  const breadcrumbItems = breadcrumbsData
    .map((breadcrumb, index) => {
      const isClickable = index < breadcrumbsData.length - 1;
      const hasColumns = breadcrumb.columns.length > 0;
      const hasFilters = ensureIsArray(breadcrumb.filters).length > 0;

      if (!hasColumns && !hasFilters) {
        return undefined;
      }

      const columnsText = breadcrumb.columns
        .map(col => col.verbose_name || col.column_name)
        .join(', ');

      const filtersText = hasFilters
        ? `(${ensureIsArray(breadcrumb.filters)
            .map(
              (filter: BinaryQueryObjectFilterClause) =>
                filter.formattedVal ?? String(filter.val),
            )
            .join(', ')})`
        : '';

      const title = `${columnsText} ${filtersText}`.trim();
      return {
        title,
        onClick: isClickable ? () => onBreadcrumbClick(index) : undefined,
      };
    })
    .filter((item): item is NonNullable<typeof item> => item !== undefined);

  const onSelection = useCallback(
    (
      newColumn: Column,
      newDrillByConfig: Required<ContextMenuFilters>['hierarchicalDrillBy'],
    ) => {
      dispatch(
        logEvent(LOG_ACTIONS_FURTHER_DRILL_BY, {
          drill_depth: drillConfigs.length + 1,
          slice_id: formData.slice_id,
        }),
      );
      setDrillConfigs(prev => [
        ...prev,
        { ...newDrillByConfig, column: newColumn },
      ]);
      setBreadcrumbsData(prev => {
        const updated = [...prev];
        updated[updated.length - 1].filters = newDrillByConfig.filters;
        return [...updated, { columns: [newColumn] }];
      });
    },
    [dispatch, drillConfigs.length, formData.slice_id],
  );

  const additionalConfig = useMemo(
    () => ({
      hierarchicalDrillBy: {
        excludedColumns: usedGroupbyColumns,
        openNewModal: false,
      },
    }),
    [usedGroupbyColumns],
  );

  const { contextMenu, inContextMenu, onContextMenu } = useContextMenu(
    0,
    drilledFormData,
    onSelection,
    ContextMenuItem.HierarchicalDrillBy,
    additionalConfig,
  );

  const chartName = useSelector<RootState, string | undefined>(state => {
    const chartLayoutItem = Object.values(state.dashboardLayout.present).find(
      layoutItem => layoutItem.meta?.chartId === formData.slice_id,
    );
    return (
      chartLayoutItem?.meta.sliceNameOverride || chartLayoutItem?.meta.sliceName
    );
  });

  useEffect(() => {
    if (drilledFormData && drillColumns.length > 0) {
      const [useLegacyApi] = getQuerySettings(drilledFormData);
      setIsChartDataLoading(true);
      setChartDataResult(undefined);
      getChartDataRequest({
        formData: drilledFormData,
      })
        .then(({ response, json }) =>
          handleChartDataResponse(response, json, useLegacyApi),
        )
        .then(queriesResponse => {
          setChartDataResult(queriesResponse);
        })
        .catch(() => {
          addDangerToast(t('Failed to load chart data.'));
        })
        .finally(() => {
          setIsChartDataLoading(false);
        });
    }
  }, [addDangerToast, drilledFormData, drillColumns.length]);

  const { metadataBar } = useDatasetMetadataBar({ dataset });

  return (
    <Modal
      css={css`
        .ant-modal-footer {
          border-top: none;
        }
      `}
      show
      onHide={onHideModal ?? (() => null)}
      name={t('Drill by (hierarchical): %s', chartName)}
      title={t('Drill by (hierarchical): %s', chartName)}
      footer={<ModalFooter formData={drilledFormData} />}
      responsive
      resizable
      resizableConfig={{
        minHeight: theme.sizeUnit * 128,
        minWidth: theme.sizeUnit * 128,
        defaultSize: {
          width: 'auto',
          height: '80vh',
        },
      }}
      draggable
      destroyOnHidden
      maskClosable={false}
    >
      <Flex
        vertical
        gap={theme.sizeUnit}
        css={css`
          height: 100%;
        `}
      >
        {metadataBar}
        <Breadcrumb
          css={css`
            margin-bottom: ${theme.sizeUnit * 2}px;
          `}
          items={breadcrumbItems}
          itemRender={(route, _, routes, paths) => {
            const isLastElement = routes.indexOf(route) === routes.length - 1;
            return isLastElement ? (
              <span data-test="hierarchical-drill-by-breadcrumb-item">
                {route.title}
                {paths}
              </span>
            ) : (
              <span
                data-test="hierarchical-drill-by-breadcrumb-item"
                role="button"
                tabIndex={0}
                onClick={route.onClick}
                css={css`
                  cursor: pointer;
                `}
              >
                {route.title}
              </span>
            );
          }}
        />
        {displayModeToggle}
        {drillColumns.length === 0 && (
          <Alert
            type="info"
            message={t(
              'Right-click on the chart to add another drill-by level',
            )}
          />
        )}
        {isChartDataLoading && drillColumns.length > 0 && <Loading />}
        {!isChartDataLoading && !chartDataResult && drillColumns.length > 0 && (
          <Alert
            type="error"
            message={t('There was an error loading the chart data')}
          />
        )}
        {drillByDisplayMode === DrillByType.Chart && chartDataResult && (
          <DrillByChart
            dataset={dataset}
            formData={drilledFormData}
            result={chartDataResult}
            onContextMenu={onContextMenu}
            inContextMenu={inContextMenu}
          />
        )}
        {drillByDisplayMode === DrillByType.Table &&
          chartDataResult &&
          resultsTable}
        {contextMenu}
      </Flex>
    </Modal>
  );
}

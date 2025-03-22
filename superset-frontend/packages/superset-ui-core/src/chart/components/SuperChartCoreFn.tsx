import React, { RefObject, useMemo } from 'react';
import { t } from '@superset-ui/core';
import { createSelector } from 'reselect';
import getChartComponentRegistry from '../registries/ChartComponentRegistrySingleton';
import getChartTransformPropsRegistry from '../registries/ChartTransformPropsRegistrySingleton';
import ChartProps from '../models/ChartProps';
import createLoadableRenderer from './createLoadableRenderer';
import { ChartType } from '../models/ChartPlugin';
import { PreTransformProps, TransformProps, PostTransformProps } from '../types/TransformFunction';
import { HandlerFunction } from '../types/Base';

function IDENTITY<T>(x: T) {
    return x;
  }
const EMPTY = () => null;

interface LoadingProps {
  error: { toString(): string };
}

interface LoadedModules {
  Chart: ChartType;
  transformProps: TransformProps;
}

interface RenderProps {
  chartProps: ChartProps;
  preTransformProps?: PreTransformProps;
  postTransformProps?: PostTransformProps;
}

const BLANK_CHART_PROPS = new ChartProps();

interface SuperChartCoreProps {
    id?: string;
    ref?: RefObject<HTMLDivElement>;
    className?: string;
    chartProps?: ChartProps | null;
    chartType: string;
    preTransformProps?: PreTransformProps;
    overrideTransformProps?: TransformProps;
    postTransformProps?: PostTransformProps;
    onRenderSuccess?: HandlerFunction;
    onRenderFailure?: HandlerFunction;
}

export type Props = SuperChartCoreProps;

const SuperChartCore = ({
  id,
  ref,
  className,
  chartProps = BLANK_CHART_PROPS,
  chartType,
  preTransformProps = IDENTITY,
  overrideTransformProps,
  postTransformProps = IDENTITY,
  onRenderSuccess,
  onRenderFailure,
}: Props) => {

  const processChartProps = useMemo(
    () => createSelector(
      [
        input => input.chartProps,
        input => input.preTransformProps,
        input => input.transformProps,
        input => input.postTransformProps,
      ],
      (chartProps, pre = IDENTITY, transform = IDENTITY, post = IDENTITY) =>
        post(transform(pre(chartProps))),
    ),
    []
  );

  const createLoadableRendererr = useMemo(
    () => createSelector(
      [
        input => input.chartType,
        input => input.overrideTransformProps,
      ],
      (chartType, overrideTransformProps) => {
        if (chartType) {
          const Renderer = createLoadableRenderer({
            loader: {
              Chart: () => getChartComponentRegistry().getAsPromise(chartType),
              transformProps: overrideTransformProps
                ? () => Promise.resolve(overrideTransformProps)
                : () => getChartTransformPropsRegistry().getAsPromise(chartType),
            },
            loading: loadingProps => renderLoading(loadingProps, chartType),
            render: renderChart,
          });

          Renderer.preload();
          return Renderer;
        }
        return EMPTY;
      }
    ),
    []
  );

  const renderChart = (loaded: LoadedModules, props: RenderProps) => {
    const { Chart, transformProps } = loaded;
    return (
      <Chart
        {...processChartProps({
          chartProps: props.chartProps,
          preTransformProps: props.preTransformProps,
          transformProps,
          postTransformProps: props.postTransformProps,
        })}
      />
    );
  };

  const renderLoading = (loadingProps: LoadingProps, chartType: string) => {
    const { error } = loadingProps;
    return error ? (
      <div className="alert alert-warning" role="alert">
        <strong>{t('ERROR')}</strong>&nbsp;
        <code>chartType=&quot;{chartType}&quot;</code> &mdash;
        {error.toString()}
      </div>
    ) : null;
  };

  const Renderer = createLoadableRendererr({ chartType, overrideTransformProps });

  if (chartProps === null) {
    return null;
  }

  return (
    <div id={id} className={className} ref={ref}>
      <Renderer
        preTransformProps={preTransformProps}
        postTransformProps={postTransformProps}
        chartProps={chartProps}
        onRenderSuccess={onRenderSuccess}
        onRenderFailure={onRenderFailure}
      />
    </div>
  );
};

export default SuperChartCore;

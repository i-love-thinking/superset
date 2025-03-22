import {
  ReactNode,
  RefObject,
  ComponentType,
  useRef,
  useMemo,
  Fragment,
} from 'react';

import {
  ErrorBoundary,
  ErrorBoundaryProps,
  FallbackProps,
} from 'react-error-boundary';
import { ParentSize } from '@visx/responsive';
import { withTheme } from '@emotion/react';
import { parseLength, Dimension } from '../../dimension';
import getChartMetadataRegistry from '../registries/ChartMetadataRegistrySingleton';
import SuperChartCore, {
  Props as SuperChartCoreProps,
} from './SuperChartCoreFn';
import DefaultFallbackComponent from './FallbackComponent';
import ChartProps, { ChartPropsConfig } from '../models/ChartProps';
import NoResultsComponent from './NoResultsComponent';

export type FallbackPropsWithDimension = FallbackProps & Partial<Dimension>;

export type WrapperProps = Dimension & {
  children: ReactNode;
};

export type Props = Omit<SuperChartCoreProps, 'chartProps'> &
  Omit<ChartPropsConfig, 'width' | 'height'> & {
    /**
     * Set this to true to disable error boundary built-in in SuperChart
     * and let the error propagate to upper level
     * and handle by yourself
     */
    disableErrorBoundary?: boolean;
    /** debounceTime to check for container resize */
    debounceTime?: number;
    /** enable "No Results" message if empty result set */
    enableNoResults?: boolean;
    /** Component to render when there are unexpected errors */
    FallbackComponent?: ComponentType<FallbackPropsWithDimension>;
    /** Event listener for unexpected errors from chart */
    onErrorBoundary?: ErrorBoundaryProps['onError'];
    /** Prop for form plugins using superchart */
    showOverflow?: boolean;
    /** Prop for popovercontainer ref */
    parentRef?: RefObject<any>;
    /** Prop for chart ref */
    inputRef?: RefObject<any>;
    /** Chart width */
    height?: number | string;
    /** Chart height */
    width?: number | string;
    /**
     * Component to wrap the actual chart
     * after the dynamic width and height are determined.
     * This can be useful for handling tooltip z-index, etc.
     * e.g. <div style={{ position: 'fixed' }} />
     * You cannot just wrap this same component outside of SuperChart
     * when using dynamic width or height
     * because it will clash with auto-sizing.
     */
    Wrapper?: ComponentType<WrapperProps>;
    /**
     * Component to display when query returns no results.
     * If not defined, NoResultsComponent is used
     */
    noResults?: ReactNode;
    /**
     * Determines is the context menu related to the chart is open
     */
    inContextMenu?: boolean;
  };

const SuperChart = (props: Props) => {
  const coreRef = useRef(null);
  const {
    id,
    className,
    chartType,
    preTransformProps,
    overrideTransformProps,
    postTransformProps,
    onRenderSuccess,
    onRenderFailure,
    disableErrorBoundary,
    FallbackComponent = DefaultFallbackComponent,
    onErrorBoundary,
    Wrapper,
    queriesData,
    enableNoResults,
    noResults,
    theme,
    width = '100%',
    height = 400,
    debounceTime,
    ...rest
  } = { ...props };

  const createChartProps = ChartProps.createSelector();

  const { BoundingBox, heightInfo, widthInfo } = useMemo(() => {
    const widthInfo = parseLength(width);
    const heightInfo = parseLength(height);
    const style = {
      height: heightInfo.isDynamic
        ? `${heightInfo.multiplier * 100}%`
        : heightInfo.value,
      width: widthInfo.isDynamic
        ? `${widthInfo.multiplier * 100}%`
        : widthInfo.value,
    };
    const BoundingBox =
      widthInfo.isDynamic &&
      heightInfo.isDynamic &&
      widthInfo.multiplier === 1 &&
      heightInfo.multiplier === 1
        ? Fragment
        : ({ children }: { children: ReactNode }) => (
            <div style={style}>{children}</div>
          );

    return { BoundingBox, heightInfo, widthInfo };
  }, [width, height]);

  const getQueryCount = () =>
    getChartMetadataRegistry().get(chartType)?.queryObjectCount ?? 1;

  const renderChart = (width: number, height: number) => {
    const chartProps = createChartProps({
      ...rest,
      queriesData,
      height,
      width,
      theme,
    });
    const noResultQueries =
      enableNoResults &&
      (!queriesData ||
        queriesData
          .slice(0, getQueryCount())
          .every(
            ({ data }) => !data || (Array.isArray(data) && data.length === 0),
          ));
    const chartWithoutWrapper = (
      <SuperChartCore
        ref={coreRef}
        id={id}
        className={className}
        chartType={chartType}
        chartProps={chartProps}
        preTransformProps={preTransformProps}
        overrideTransformProps={overrideTransformProps}
        postTransformProps={postTransformProps}
        onRenderSuccess={onRenderSuccess}
        onRenderFailure={onRenderFailure}
      />
    );
    const chart = noResultQueries ? (
      noResults || (
        <NoResultsComponent
          id={id}
          className={className}
          height={height}
          width={width}
        />
      )
    ) : Wrapper ? (
      <Wrapper width={width} height={height}>
        {chartWithoutWrapper}
      </Wrapper>
    ) : (
      chartWithoutWrapper
    );

    return disableErrorBoundary ? (
      chart
    ) : (
      <ErrorBoundary
        FallbackComponent={props => (
          <FallbackComponent width={width} height={height} {...props} />
        )}
        onError={onErrorBoundary}
      >
        {chart}
      </ErrorBoundary>
    );
  };

  return widthInfo.isDynamic || heightInfo.isDynamic ? (
    <BoundingBox>
      <ParentSize debounceTime={debounceTime}>
        {({ width, height }) =>
          renderChart(
            widthInfo.isDynamic ? Math.floor(width) : widthInfo.value,
            heightInfo.isDynamic ? Math.floor(height) : heightInfo.value,
          )
        }
      </ParentSize>
    </BoundingBox>
  ) : (
    renderChart(widthInfo.value, heightInfo.value)
  );
};

export default withTheme(SuperChart as ComponentType);

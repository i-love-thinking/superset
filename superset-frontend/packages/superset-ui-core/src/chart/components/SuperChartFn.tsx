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
import { ParentSize } from '@vx/responsive';
import { withTheme } from '@emotion/react';
import { parseLength, Dimension } from '../../dimension';
import getChartMetadataRegistry from '../registries/ChartMetadataRegistrySingleton';
import SuperChartCore, { Props as SuperChartCoreProps } from './SuperChartCore';
import DefaultFallbackComponent from './FallbackComponent';
import ChartProps, { ChartPropsConfig } from '../models/ChartProps';
import NoResultsComponent from './NoResultsComponent';

const defaultProps = {
  FallbackComponent: DefaultFallbackComponent,
  height: 400,
  width: '100%',
  enableNoResults: true,
};

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
    FallbackComponent,
    onErrorBoundary,
    Wrapper,
    queriesData,
    enableNoResults,
    noResults,
    theme,
    width,
    height,
    debounceTime,
  } = { ...defaultProps, ...props };

  const chartProps = useMemo(
    () =>
      ChartProps.createSelector()({
        ...props,
        queriesData,
        height,
        width,
        theme,
      }),
    [props, queriesData, height, width, theme]
  );

  const { BoundingBox, heightInfo, widthInfo } = useMemo(() => {
    const widthInfo = parseLength(width);
    const heightInfo = parseLength(height);
    const style = {
      height: heightInfo.isDynamic ? `${heightInfo.multiplier * 100}%` : heightInfo.value,
      width: widthInfo.isDynamic ? `${widthInfo.multiplier * 100}%` : widthInfo.value,
    };
    const BoundingBox = widthInfo.isDynamic || heightInfo.isDynamic ?
      ({ children }: { children: ReactNode }) => <div style={style}>{children}</div> : Fragment;
    return { BoundingBox, heightInfo, widthInfo };
  }, [width, height]);

  const getQueryCount = () =>
    getChartMetadataRegistry().get(chartType)?.queryObjectCount ?? 1;

  const renderChart = (chartWidth, chartHeight) => {
    const noResultQueries =
      enableNoResults &&
      (!queriesData ||
        queriesData
          .slice(0, getQueryCount())
          .every(({ data }) => !data || (Array.isArray(data) && data.length === 0)));

    const chart = noResultQueries ? (
      noResults || <NoResultsComponent id={id} className={className} height={chartHeight} width={chartWidth} />
    ) : (
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

    return disableErrorBoundary ? chart : (
      <ErrorBoundary FallbackComponent={(props) => <FallbackComponent width={chartWidth} height={chartHeight} {...props} />} onError={onErrorBoundary}>
        {chart}
      </ErrorBoundary>
    );
  };

  return widthInfo.isDynamic || heightInfo.isDynamic ? (
    <BoundingBox>
      <ParentSize debounceTime={debounceTime}>
        {({ width, height }) => renderChart(
          widthInfo.isDynamic ? Math.floor(width) : widthInfo.value,
          heightInfo.isDynamic ? Math.floor(height) : heightInfo.value
        )}
      </ParentSize>
    </BoundingBox>
  ) : renderChart(widthInfo.value, heightInfo.value);
};

export default withTheme(SuperChart);

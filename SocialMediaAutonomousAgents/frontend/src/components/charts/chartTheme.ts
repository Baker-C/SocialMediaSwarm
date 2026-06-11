/* Shared recharts styling for the tactical ops theme. */

import type React from 'react';

export const CHART_COLORS = {
  orange: '#f97316',
  white: '#ffffff',
  red: '#ef4444',
  neutral: '#a3a3a3',
  yellow: '#eab308',
} as const;

export const CHART_SERIES_PALETTE: string[] = [
  CHART_COLORS.orange,
  CHART_COLORS.white,
  CHART_COLORS.red,
  CHART_COLORS.neutral,
  CHART_COLORS.yellow,
];

export const CHART_GRID_STROKE = '#404040';

export const CHART_AXIS_TICK = { fontSize: 11, fill: '#737373' };

export const CHART_AXIS_LINE = { stroke: '#404040' };

export const CHART_TOOLTIP_CONTENT_STYLE: React.CSSProperties = {
  backgroundColor: '#171717',
  border: '1px solid #404040',
  borderRadius: 4,
  fontSize: 12,
  fontFamily: 'inherit',
};

export const CHART_TOOLTIP_LABEL_STYLE: React.CSSProperties = {
  color: '#a3a3a3',
};

export const CHART_LEGEND_STYLE: React.CSSProperties = {
  fontSize: 12,
  color: '#a3a3a3',
};

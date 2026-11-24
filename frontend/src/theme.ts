/**
 * Colours for SVG charts (Recharts): SVG presentation attributes cannot read CSS var(), so charts ask the
 * design tokens (design.css :root) for their current values. No colour is written here.
 * In tests (jsdom has no stylesheet) a token is empty and the chart falls back to currentColor.
 */
export function themeColor(token: string): string {
  if (typeof document === 'undefined') return 'currentColor'
  return getComputedStyle(document.documentElement).getPropertyValue(token).trim() || 'currentColor'
}

/** Everything a line or bar chart needs, read once per render. */
export function chartColors() {
  return {
    grid: themeColor('--chart-grid'),
    tick: themeColor('--text-faint'),
    label: themeColor('--text-muted'),
    line: themeColor('--accent'),
    surface: themeColor('--surface-1'),
    tooltipBg: themeColor('--surface-2'),
    tooltipBorder: themeColor('--border-strong'),
    tooltipText: themeColor('--text-strong'),
    warn: themeColor('--warn'),
    danger: themeColor('--danger'),
    info: themeColor('--info'),
    fontFamily: themeColor('--font-mono'),
  }
}

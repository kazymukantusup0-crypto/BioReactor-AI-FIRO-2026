// design-v3 line icons: our own drawings, outline in currentColor (black on paper cards, white on dark ones)
// plus a lime accent shape (.li-accent). 32×32, stroke 1.75. No other product's art.
import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement> & { size?: number }
const base = (size: number, rest: SVGProps<SVGSVGElement>) => ({
  width: size, height: size, viewBox: '0 0 32 32', fill: 'none', stroke: 'currentColor', strokeWidth: 1.75,
  strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true, ...rest,
})

export function IconThermo({ size = 32, ...rest }: IconProps) {
  return <svg {...base(size, rest)} className={`li ${rest.className ?? ''}`}>
    <circle className="li-accent" cx="14" cy="23" r="3.2" stroke="none" />
    <path d="M11 18.5V6.5a3 3 0 0 1 6 0v12a5.5 5.5 0 1 1-6 0Z" /><path d="M14 20V10" /><path d="M21 8h4M21 12h3M21 16h4" />
  </svg>
}

export function IconGas({ size = 32, ...rest }: IconProps) {
  return <svg {...base(size, rest)} className={`li ${rest.className ?? ''}`}>
    <circle className="li-accent" cx="20.5" cy="9" r="3.5" stroke="none" />
    <circle cx="20.5" cy="9" r="3.5" /><circle cx="11" cy="14" r="5" /><circle cx="17" cy="23" r="4" /><circle cx="8" cy="25" r="1.6" />
  </svg>
}

export function IconLeak({ size = 32, ...rest }: IconProps) {
  return <svg {...base(size, rest)} className={`li ${rest.className ?? ''}`}>
    <path className="li-accent" d="M16 9c2.4 2.6 3.6 4.6 3.6 6.4a3.6 3.6 0 0 1-7.2 0c0-1.8 1.2-3.8 3.6-6.4Z" stroke="none" />
    <path d="M16 3.5 26 7v8.2c0 6-4.2 10.6-10 13.3C10.2 25.8 6 21.2 6 15.2V7Z" />
    <path d="M16 9c2.4 2.6 3.6 4.6 3.6 6.4a3.6 3.6 0 0 1-7.2 0c0-1.8 1.2-3.8 3.6-6.4Z" />
  </svg>
}

export function IconDrop({ size = 32, ...rest }: IconProps) {
  return <svg {...base(size, rest)} className={`li ${rest.className ?? ''}`}>
    <path className="li-accent" d="M8.6 19.5h14.8a7.4 7.4 0 0 1-14.8 0Z" stroke="none" />
    <path d="M16 4c5 5.6 7.5 10 7.5 14.2a7.5 7.5 0 0 1-15 0C8.5 14 11 9.6 16 4Z" /><path d="M8.6 19.5h14.8" />
  </svg>
}

export function IconRelay({ size = 32, ...rest }: IconProps) {
  return <svg {...base(size, rest)} className={`li ${rest.className ?? ''}`}>
    <circle className="li-accent" cx="22" cy="16" r="3" stroke="none" />
    <rect x="4" y="9" width="24" height="14" rx="7" /><circle cx="22" cy="16" r="3" /><path d="M9 16h6" />
  </svg>
}

export function IconChip({ size = 32, ...rest }: IconProps) {
  return <svg {...base(size, rest)} className={`li ${rest.className ?? ''}`}>
    <rect className="li-accent" x="12" y="12" width="8" height="8" rx="1.5" stroke="none" />
    <rect x="8" y="8" width="16" height="16" rx="3" /><rect x="12" y="12" width="8" height="8" rx="1.5" />
    <path d="M12 4v4M16 4v4M20 4v4M12 24v4M16 24v4M20 24v4M4 12h4M4 16h4M4 20h4M24 12h4M24 16h4M24 20h4" />
  </svg>
}

/** The four-point star used as a small decoration (✦), drawn, not a font glyph. */
export function Sparkle({ size = 14, ...rest }: IconProps) {
  return <svg width={size} height={size} viewBox="0 0 16 16" aria-hidden="true" {...rest} className={`li-sparkle ${rest.className ?? ''}`}>
    <path d="M8 0c.6 4.2 3.2 7 8 8-4.8 1-7.4 3.8-8 8-.6-4.2-3.2-7-8-8 4.8-1 7.4-3.8 8-8Z" />
  </svg>
}

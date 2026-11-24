// design-v3 shared pieces: a section title on the lime marker, a status word with its icon.
import type { ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from 'lucide-react'
import type { Level } from './reactorApi'
import { tr } from './i18n'

const LEVEL_ICON = { ok: CheckCircle2, warn: AlertTriangle, danger: XCircle, unknown: HelpCircle } as const

/** A status is never colour alone: an icon and a word (норма / внимание / авария / нет данных). */
export function LevelWord({ level }: { level: Level }) {
  const Icon = LEVEL_ICON[level]
  return <span className={`v3-level v3-level-${level}`}><Icon size={16} aria-hidden="true" />{tr(`ov.level.${level}`)}</span>
}

/** A section title on the lime marker (black text on lime). */
export function Marked({ children, as: Tag = 'h2', id, className = '' }: { children: ReactNode; as?: 'h1' | 'h2'; id?: string; className?: string }) {
  return <Tag className={`v3-section-title ${className}`} id={id}><span className="v3-mark">{children}</span></Tag>
}

import { t } from '../lib/language.ts'
import './ModifiedMark.css'

export function ModifiedMark({ show }: { show: boolean }) {
  if (!show) {
    return null
  }
  return (
    <span className="modified-mark" aria-hidden="true">
      <span className="modified-mark__dot" />
      <span className="modified-mark__text">{t.modified}</span>
    </span>
  )
}

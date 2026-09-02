import { useEffect, useId, useState } from 'react'
import { t } from '../lib/language.ts'
import { ConfirmDialog } from './ConfirmDialog.tsx'

export function ReprocessConflictDialog({
  open,
  web = false,
  unsaved = false,
  saved = false,
  onCancel,
  onOverwrite,
  onCreateNew,
}: {
  open: boolean
  web?: boolean
  unsaved?: boolean
  saved?: boolean
  onCancel: () => void
  onOverwrite: () => void
  onCreateNew: (prefix: string) => void
}) {
  const prefixId = useId()
  const [prefix, setPrefix] = useState(t.reprocessTitlePrefix)

  useEffect(() => {
    if (open) {
      setPrefix(t.reprocessTitlePrefix)
    }
  }, [open])

  return (
    <ConfirmDialog
      open={open}
      title={t.confirmReprocessConflictTitle}
      message={
        <>
          <p>{t.confirmReprocessConflictBody}</p>
          {unsaved ? <p>{t.confirmReprocessConflictUnsaved}</p> : null}
          {saved ? <p>{t.confirmReprocessConflictSaved}</p> : null}
          {web ? <p>{t.confirmReprocessConflictWeb}</p> : null}
          <div className="confirm-dialog__field">
            <label htmlFor={prefixId}>{t.confirmReprocessPrefixLabel}</label>
            <input
              id={prefixId}
              className="confirm-dialog__input"
              dir="auto"
              value={prefix}
              onChange={(event) => setPrefix(event.target.value)}
            />
          </div>
        </>
      }
      cancelLabel={t.confirmCancel}
      confirmLabel={t.confirmReprocessOverwrite}
      extra={
        <button
          type="button"
          className="confirm-dialog__confirm confirm-dialog__confirm--secondary"
          onClick={() => onCreateNew(prefix)}
        >
          {t.confirmReprocessCreateNew}
        </button>
      }
      danger
      onCancel={onCancel}
      onConfirm={onOverwrite}
    />
  )
}

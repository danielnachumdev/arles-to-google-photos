import { useId, useRef, useState, type KeyboardEvent } from 'react'
import './HintTooltip.css'

/** Small info control: in-app tooltip on hover and keyboard focus. */
export function HintTooltip({
  label,
  text,
}: {
  label: string
  text: string
}) {
  const tooltipId = useId()
  const triggerRef = useRef<HTMLButtonElement>(null)
  const [open, setOpen] = useState(false)

  function show() {
    setOpen(true)
  }

  function hideUnlessFocused() {
    if (triggerRef.current === document.activeElement) {
      return
    }
    setOpen(false)
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== 'Escape' || !open) {
      return
    }
    event.preventDefault()
    setOpen(false)
    triggerRef.current?.blur()
  }

  return (
    <span className="hint-tooltip">
      <button
        ref={triggerRef}
        type="button"
        className="hint-tooltip__trigger"
        aria-label={label}
        aria-describedby={open ? tooltipId : undefined}
        onMouseEnter={show}
        onMouseLeave={hideUnlessFocused}
        onFocus={show}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      >
        <span aria-hidden="true">i</span>
      </button>
      <span
        id={tooltipId}
        role="tooltip"
        hidden={!open}
        className="hint-tooltip__bubble"
      >
        {text}
      </span>
    </span>
  )
}

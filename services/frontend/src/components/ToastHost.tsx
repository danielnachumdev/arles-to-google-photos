import { useSyncExternalStore, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { useLanguage } from '../lib/language.ts'
import { getToasts, resolveToastActions, subscribeToasts, toast } from '../lib/toast.ts'
import './ToastHost.css'

export function ToastHost() {
  const { t } = useLanguage()
  const items = useSyncExternalStore(subscribeToasts, getToasts, getToasts)

  return (
    <div className="toast-host">
      {items.map((item) => {
        const actions = resolveToastActions(item)
        return (
          <div
            key={item.id}
            className={`toast toast--${item.type}`}
            role="status"
            aria-atomic="true"
          >
            {item.durationMs > 0 ? (
              <span
                className="toast__progress"
                aria-hidden="true"
                style={{ '--toast-duration': `${item.durationMs}ms` } as CSSProperties}
              />
            ) : null}
            <span className="toast__swatch" aria-hidden="true" />
            <div className="toast__body">
              <p className="toast__message" dir="auto">
                {item.message}
              </p>
              {actions.length > 0 ? (
                <div className="toast__actions">
                  {actions.map((action) =>
                    action.external ? (
                      <a
                        key={`${action.href}:${action.label}`}
                        className="toast__link"
                        href={action.href}
                        target="_blank"
                        rel="noreferrer"
                        onClick={() => toast.dismiss(item.id)}
                      >
                        {action.label}
                      </a>
                    ) : (
                      <Link
                        key={`${action.href}:${action.label}`}
                        className="toast__link"
                        to={action.href}
                        onClick={() => toast.dismiss(item.id)}
                      >
                        {action.label}
                      </Link>
                    ),
                  )}
                </div>
              ) : null}
            </div>
            <button
              type="button"
              className="toast__dismiss"
              onClick={() => toast.dismiss(item.id)}
              aria-label={t.toastDismissAria}
            >
              ×
            </button>
          </div>
        )
      })}
    </div>
  )
}

import { Link } from 'react-router-dom'
import { t, useLanguage } from '../lib/language.ts'
import './NotFoundPage.css'

export function NotFoundPage() {
  useLanguage()
  return (
    <section className="not-found" aria-labelledby="not-found-heading">
      <div className="not-found__stage">
        <p className="not-found__code">404</p>
        <h1 id="not-found-heading" className="not-found__heading">
          {t.notFoundHeading}
        </h1>
        <p className="not-found__lede">{t.notFoundLede}</p>
        <p className="not-found__home">
          <Link to="/">{t.notFoundHome}</Link>
        </p>
      </div>
    </section>
  )
}

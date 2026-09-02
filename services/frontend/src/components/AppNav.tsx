import { Link, NavLink } from 'react-router-dom'
import './AppNav.css'
import { t } from '../lib/language.ts'
import { APP_VERSION } from '../version.ts'

export function AppNav() {
  return (
    <header className="app-nav">
      <div className="app-nav__brand">
        <p className="app-nav__kicker">{t.kicker}</p>
        <h1 className="app-nav__title">
          <Link to="/" className="app-nav__title-link">
            {t.appTitle}
          </Link>
          <span className="app-nav__version" dir="ltr" title={t.appVersionLabel(APP_VERSION)}>
            {t.settingsVersionValue(APP_VERSION)}
          </span>
        </h1>
      </div>
      <nav className="app-nav__links" aria-label={t.navAria}>
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            isActive ? 'app-nav__link app-nav__link--active' : 'app-nav__link'
          }
        >
          {t.navHome}
        </NavLink>
        <NavLink
          to="/albums"
          end
          className={({ isActive }) =>
            isActive ? 'app-nav__link app-nav__link--active' : 'app-nav__link'
          }
        >
          {t.navAlbums}
        </NavLink>
        <NavLink
          to="/jobs"
          end
          className={({ isActive }) =>
            isActive ? 'app-nav__link app-nav__link--active' : 'app-nav__link'
          }
        >
          {t.navJobs}
        </NavLink>
        <NavLink
          to="/settings"
          end
          className={({ isActive }) =>
            isActive ? 'app-nav__link app-nav__link--active' : 'app-nav__link'
          }
        >
          {t.navSettings}
        </NavLink>
      </nav>
    </header>
  )
}

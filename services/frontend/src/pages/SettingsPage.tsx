import { useEffect, useId, useState } from 'react'
import { MigrationClient } from '../api/client.ts'
import { HintTooltip } from '../components/HintTooltip.tsx'
import { LoadingSpinner } from '../components/LoadingSpinner.tsx'
import { useAppearance } from '../lib/appearance.ts'
import { formatApiError } from '../lib/formatApiError.ts'
import { clearImportCookies } from '../lib/settings.ts'
import { clearGooglePhotosSession } from '../storage/googlePhotosSession.ts'
import { messages, useLanguage, type AppLanguage } from '../lib/language.ts'
import { toast } from '../lib/toast.ts'
import { APP_VERSION } from '../version.ts'
import './SettingsPage.css'

const client = new MigrationClient()

export function SettingsPage() {
  const { language, t, setLanguage } = useLanguage()
  const { colorScheme, setColorScheme } = useAppearance()
  const maxConcurrentId = useId()
  const [draftLanguage, setDraftLanguage] = useState<AppLanguage>(language)
  const [maxConcurrent, setMaxConcurrent] = useState('3')
  const [queueCounts, setQueueCounts] = useState<{
    pending: number
    running: number
    waiting: number
  } | null>(null)
  const [appVersion, setAppVersion] = useState(APP_VERSION)
  const [saving, setSaving] = useState(false)
  const [queueError, setQueueError] = useState<string | null>(null)

  useEffect(() => {
    setDraftLanguage(language)
  }, [language])

  useEffect(() => {
    let cancelled = false
    void client
      .getSettings()
      .then((settings) => {
        if (cancelled) {
          return
        }
        setMaxConcurrent(String(settings.max_concurrent_jobs))
        setQueueCounts({
          pending: settings.pending,
          running: settings.running,
          waiting: settings.waiting ?? 0,
        })
        setQueueError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return
        }
        setQueueError(formatApiError(err))
      })
    void client
      .getVersion()
      .then((version) => {
        if (!cancelled) {
          setAppVersion(version)
        }
      })
      .catch(() => {
        /* keep bundled APP_VERSION */
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function saveSettings() {
    const catalog = messages[draftLanguage]
    setLanguage(draftLanguage)

    const parsed = Number.parseInt(maxConcurrent, 10)
    if (!Number.isFinite(parsed)) {
      setQueueError('invalid number')
      toast.bad(catalog.settingsOrchestratorError('invalid number'))
      return
    }
    setSaving(true)
    setQueueError(null)
    try {
      const saved = await client.patchSettings(parsed)
      setMaxConcurrent(String(saved.max_concurrent_jobs))
      setQueueCounts({
        pending: saved.pending,
        running: saved.running,
        waiting: saved.waiting ?? 0,
      })
      toast.good(catalog.settingsOrchestratorSaved)
    } catch (err: unknown) {
      const detail = formatApiError(err, catalog)
      setQueueError(detail)
      toast.bad(catalog.settingsOrchestratorError(detail))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="settings-page">
      <div className="settings-page__stage">
        <h2 className="settings-page__heading">{t.settingsHeading}</h2>
        <p className="settings-page__lede">{t.settingsLede}</p>
        <form
          className="settings-page__form"
          onSubmit={(event) => {
            event.preventDefault()
            void saveSettings()
          }}
        >
          <fieldset className="settings-page__fieldset">
            <legend className="settings-page__legend">{t.languageLabel}</legend>
            <div className="settings-page__options">
              <label className="settings-page__option">
                <input
                  type="radio"
                  name="language"
                  value="he"
                  checked={draftLanguage === 'he'}
                  onChange={() => setDraftLanguage('he')}
                />
                עברית
              </label>
              <label className="settings-page__option">
                <input
                  type="radio"
                  name="language"
                  value="en"
                  checked={draftLanguage === 'en'}
                  onChange={() => setDraftLanguage('en')}
                />
                English
              </label>
            </div>
          </fieldset>
          <fieldset className="settings-page__fieldset">
            <legend className="settings-page__legend">{t.appearanceLabel}</legend>
            <p className="settings-page__hint">{t.appearanceHint}</p>
            <div className="settings-page__options">
              <label className="settings-page__option">
                <input
                  type="radio"
                  name="appearance"
                  value="light"
                  checked={colorScheme === 'light'}
                  onChange={() => setColorScheme('light')}
                />
                {t.appearanceLight}
              </label>
              <label className="settings-page__option">
                <input
                  type="radio"
                  name="appearance"
                  value="dark"
                  checked={colorScheme === 'dark'}
                  onChange={() => setColorScheme('dark')}
                />
                {t.appearanceDark}
              </label>
            </div>
          </fieldset>
          <fieldset className="settings-page__fieldset">
          <legend className="settings-page__legend">{t.settingsOrchestratorHeading}</legend>
          <p className="settings-page__hint">{t.settingsMaxConcurrentHint}</p>
          {queueCounts ? (
            <p className="settings-page__hint" dir="ltr">
              {t.jobsQueueSummary(
                queueCounts.running,
                queueCounts.pending,
                queueCounts.waiting,
                Number.parseInt(maxConcurrent, 10) || 0,
              )}
            </p>
          ) : !queueError ? (
            <LoadingSpinner label={t.loadingSettings} />
          ) : null}
            <div className="settings-page__fields">
              <div className="settings-page__field">
                <span className="settings-page__field-heading">
                  <label htmlFor={maxConcurrentId}>{t.settingsMaxConcurrentLabel}</label>
                  <HintTooltip
                    label={t.settingsMaxConcurrentInfoAria}
                    text={t.settingsMaxConcurrentTooltip}
                  />
                </span>
                <input
                  id={maxConcurrentId}
                  className="settings-page__input"
                  dir="ltr"
                  type="number"
                  name="max-concurrent-jobs"
                  min={1}
                  max={32}
                  step={1}
                  value={maxConcurrent}
                  onChange={(event) => setMaxConcurrent(event.target.value)}
                />
              </div>
            </div>
            {queueError ? (
              <p className="settings-page__error" role="alert" dir="auto">
                {t.settingsOrchestratorError(queueError)}
              </p>
            ) : null}
          </fieldset>
          <div className="settings-page__actions">
            <button type="submit" className="settings-page__button" disabled={saving}>
              {saving ? t.saving : t.save}
            </button>
          </div>
        </form>
        <fieldset className="settings-page__fieldset">
          <legend className="settings-page__legend">{t.settingsClearCookies}</legend>
          <p className="settings-page__hint">{t.settingsClearCookiesHint}</p>
          <button
            type="button"
            className="settings-page__button settings-page__button--secondary"
            onClick={clearImportCookies}
          >
            {t.settingsClearCookies}
          </button>
        </fieldset>
        <fieldset className="settings-page__fieldset">
          <legend className="settings-page__legend">{t.settingsSignOutGoogle}</legend>
          <p className="settings-page__hint">{t.settingsSignOutGoogleHint}</p>
          <button
            type="button"
            className="settings-page__button settings-page__button--secondary"
            onClick={clearGooglePhotosSession}
          >
            {t.settingsSignOutGoogle}
          </button>
        </fieldset>
        <fieldset className="settings-page__fieldset">
          <legend className="settings-page__legend">{t.settingsVersionHeading}</legend>
          <p className="settings-page__hint">{t.settingsVersionHint}</p>
          <p className="settings-page__version" dir="ltr">
            {t.settingsVersionValue(appVersion)}
          </p>
        </fieldset>
      </div>
    </section>
  )
}

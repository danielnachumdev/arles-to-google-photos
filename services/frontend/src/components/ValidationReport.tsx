import type { ValidationReport as Report } from '../api/types.ts'
import { t } from '../lib/language.ts'
import './ValidationReport.css'

function mismatchFieldLabel(field: string): string {
  if (field === 'caption') {
    return t.validationMismatchCaption
  }
  if (field === 'size') {
    return t.validationMismatchSize
  }
  if (field === 'size_unavailable') {
    return t.validationMismatchSizeUnavailable
  }
  return field
}

export function ValidationReportView({ report }: { report: Report }) {
  const summary = report.summary ?? {}
  return (
    <div className="validation-report">
      <h2 className="validation-report__heading">{t.validationReportHeading}</h2>
      <p
        className={
          report.identical
            ? 'validation-report__verdict validation-report__verdict--ok'
            : 'validation-report__verdict validation-report__verdict--diff'
        }
        dir="auto"
      >
        {report.identical ? t.validationIdentical : t.validationDifferences}
      </p>
      <ul className="validation-report__summary">
        <li>{t.validationSummaryMatched(summary.matched ?? 0)}</li>
        <li>{t.validationSummaryOnlyRemote(summary.only_remote ?? 0)}</li>
        <li>{t.validationSummaryOnlyPhotos(summary.only_photos ?? 0)}</li>
        <li>{t.validationSummaryMismatches(summary.content_mismatches ?? 0)}</li>
      </ul>
      {report.warnings && report.warnings.length > 0 ? (
        <ul className="validation-report__warnings">
          {report.warnings.map((warning) => (
            <li key={warning} dir="auto">
              {warning}
            </li>
          ))}
        </ul>
      ) : null}

      {(report.matched?.length ?? 0) > 0 ? (
        <section className="validation-report__section">
          <h3 className="validation-report__subheading">{t.validationMatchedHeading}</h3>
          <ul className="validation-report__albums">
            {report.matched?.map((album) => (
              <li key={album.title_id} className="validation-report__album">
                <div className="validation-report__album-title" dir="auto">
                  <strong>{album.title || album.title_id}</strong>{' '}
                  <span>
                    {album.identical
                      ? t.validationAlbumIdentical
                      : t.validationAlbumDiff}
                  </span>
                </div>
                {!album.identical ? (
                  <ul className="validation-report__details">
                    {(album.only_remote_items ?? []).map((id) => (
                      <li key={`r-${id}`} dir="ltr">
                        {t.validationItemOnlyRemote}: {id}
                      </li>
                    ))}
                    {(album.only_photos_items ?? []).map((id) => (
                      <li key={`p-${id}`} dir="ltr">
                        {t.validationItemOnlyPhotos}: {id}
                      </li>
                    ))}
                    {(album.mismatches ?? []).map((m) => (
                      <li key={`${m.item_id}-${m.field}`} dir="ltr">
                        {m.item_id}: {mismatchFieldLabel(m.field)} (
                        {String(m.remote ?? '—')} → {String(m.photos ?? '—')})
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {(report.only_remote?.length ?? 0) > 0 ? (
        <section className="validation-report__section">
          <h3 className="validation-report__subheading">
            {t.validationOnlyRemoteHeading}
          </h3>
          <ul className="validation-report__albums">
            {report.only_remote?.map((album) => (
              <li key={album.title_id} dir="auto">
                {album.title || album.title_id}
                {album.url ? (
                  <>
                    {' · '}
                    <a href={album.url} target="_blank" rel="noreferrer" dir="ltr">
                      {album.url}
                    </a>
                  </>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {(report.only_photos?.length ?? 0) > 0 ? (
        <section className="validation-report__section">
          <h3 className="validation-report__subheading">
            {t.validationOnlyPhotosHeading}
          </h3>
          <ul className="validation-report__albums">
            {report.only_photos?.map((album) => (
              <li key={album.title_id} dir="auto">
                {album.title || album.title_id}
                {album.product_url ? (
                  <>
                    {' · '}
                    <a
                      href={album.product_url}
                      target="_blank"
                      rel="noreferrer"
                      dir="ltr"
                    >
                      {album.product_url}
                    </a>
                  </>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}

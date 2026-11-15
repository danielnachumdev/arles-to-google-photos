import { useEffect, useMemo, useState } from 'react'
import type { ValidationReport as Report } from '../api/types.ts'
import {
  buildValidationAlbumEntries,
  defaultValidationAlbumKey,
  filterValidationAlbums,
  formatValidationValue,
  type ValidationAlbumEntry,
  type ValidationAlbumFilter,
} from '../lib/validationAlbums.ts'
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

function albumKindLabel(entry: ValidationAlbumEntry): string {
  if (entry.kind === 'only_remote') {
    return t.validationOnlyRemoteHeading
  }
  if (entry.kind === 'only_photos') {
    return t.validationOnlyPhotosHeading
  }
  return entry.hasIssues ? t.validationAlbumDiff : t.validationAlbumIdentical
}

function AlbumListButton({
  entry,
  selected,
  onSelect,
}: {
  entry: ValidationAlbumEntry
  selected: boolean
  onSelect: (key: string) => void
}) {
  return (
    <button
      type="button"
      className={[
        'validation-report__album-btn',
        selected ? 'validation-report__album-btn--selected' : '',
        entry.hasIssues ? 'validation-report__album-btn--issue' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      aria-current={selected ? 'true' : undefined}
      onClick={() => onSelect(entry.key)}
    >
      <span className="validation-report__album-btn-title" dir="auto">
        {entry.title}
      </span>
      <span className="validation-report__album-btn-meta">
        <span
          className={[
            'validation-report__badge',
            entry.hasIssues
              ? 'validation-report__badge--diff'
              : 'validation-report__badge--ok',
          ].join(' ')}
        >
          {albumKindLabel(entry)}
        </span>
        {entry.kind !== 'matched' && entry.itemCount != null ? (
          <span className="validation-report__issue-count" dir="ltr">
            {t.validationItemCount(entry.itemCount)}
          </span>
        ) : null}
        {entry.kind === 'matched' && entry.hasIssues && entry.issueCount > 0 ? (
          <span className="validation-report__issue-count" dir="ltr">
            {t.validationIssueCount(entry.issueCount)}
          </span>
        ) : null}
      </span>
    </button>
  )
}

function ItemChipList({ ids, empty }: { ids: string[]; empty: string }) {
  if (ids.length === 0) {
    return <p className="validation-report__empty-note">{empty}</p>
  }
  return (
    <ul className="validation-report__chips">
      {ids.map((id) => (
        <li key={id} className="validation-report__chip" dir="ltr">
          {id}
        </li>
      ))}
    </ul>
  )
}

function AlbumDetail({ entry }: { entry: ValidationAlbumEntry }) {
  if (entry.kind === 'only_remote' && entry.side) {
    return (
      <div className="validation-report__detail">
        <header className="validation-report__detail-header">
          <h3 className="validation-report__detail-title" dir="auto">
            {entry.title}
          </h3>
          <p className="validation-report__detail-lede">{t.validationOnlyRemoteLede}</p>
          {entry.itemCount != null ? (
            <p className="validation-report__detail-meta" dir="ltr">
              {t.validationItemCount(entry.itemCount)}
            </p>
          ) : null}
          {entry.side.url ? (
            <a
              className="validation-report__ext-link"
              href={entry.side.url}
              target="_blank"
              rel="noreferrer"
              dir="ltr"
            >
              {t.validationOpenRemote}
            </a>
          ) : null}
        </header>
      </div>
    )
  }

  if (entry.kind === 'only_photos' && entry.side) {
    return (
      <div className="validation-report__detail">
        <header className="validation-report__detail-header">
          <h3 className="validation-report__detail-title" dir="auto">
            {entry.title}
          </h3>
          <p className="validation-report__detail-lede">{t.validationOnlyPhotosLede}</p>
          {entry.itemCount != null ? (
            <p className="validation-report__detail-meta" dir="ltr">
              {t.validationItemCount(entry.itemCount)}
            </p>
          ) : null}
          {entry.side.product_url ? (
            <a
              className="validation-report__ext-link"
              href={entry.side.product_url}
              target="_blank"
              rel="noreferrer"
              dir="ltr"
            >
              {t.validationOpenPhotos}
            </a>
          ) : null}
        </header>
      </div>
    )
  }

  const album = entry.matched
  if (!album) {
    return null
  }

  const onlyRemote = album.only_remote_items ?? []
  const onlyPhotos = album.only_photos_items ?? []
  const mismatches = album.mismatches ?? []

  return (
    <div className="validation-report__detail">
      <header className="validation-report__detail-header">
        <h3 className="validation-report__detail-title" dir="auto">
          {entry.title}
        </h3>
        <p
          className={
            album.identical
              ? 'validation-report__detail-lede validation-report__detail-lede--ok'
              : 'validation-report__detail-lede validation-report__detail-lede--diff'
          }
        >
          {album.identical
            ? t.validationAlbumIdenticalLede
            : t.validationAlbumDiffLede(entry.issueCount)}
        </p>
        <div className="validation-report__detail-links">
          {album.remote_url ? (
            <a
              className="validation-report__ext-link"
              href={album.remote_url}
              target="_blank"
              rel="noreferrer"
              dir="ltr"
            >
              {t.validationOpenRemote}
            </a>
          ) : null}
          {album.photos_product_url ? (
            <a
              className="validation-report__ext-link"
              href={album.photos_product_url}
              target="_blank"
              rel="noreferrer"
              dir="ltr"
            >
              {t.validationOpenPhotos}
            </a>
          ) : null}
        </div>
      </header>

      {album.identical ? null : (
        <div className="validation-report__compare">
          <section className="validation-report__panel">
            <h4 className="validation-report__panel-title">{t.validationItemOnlyRemote}</h4>
            <ItemChipList ids={onlyRemote} empty={t.validationNoItemsInSection} />
          </section>
          <section className="validation-report__panel">
            <h4 className="validation-report__panel-title">{t.validationItemOnlyPhotos}</h4>
            <ItemChipList ids={onlyPhotos} empty={t.validationNoItemsInSection} />
          </section>
          <section className="validation-report__panel validation-report__panel--wide">
            <h4 className="validation-report__panel-title">{t.validationFieldMismatches}</h4>
            {mismatches.length === 0 ? (
              <p className="validation-report__empty-note">{t.validationNoItemsInSection}</p>
            ) : (
              <div className="validation-report__table-wrap">
                <table className="validation-report__table">
                  <thead>
                    <tr>
                      <th scope="col">{t.validationColItem}</th>
                      <th scope="col">{t.validationColField}</th>
                      <th scope="col">{t.validationColRemote}</th>
                      <th scope="col">{t.validationColPhotos}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mismatches.map((row) => (
                      <tr key={`${row.item_id}-${row.field}`}>
                        <td dir="ltr">{row.item_id}</td>
                        <td>{mismatchFieldLabel(row.field)}</td>
                        <td dir="auto">{formatValidationValue(row.remote)}</td>
                        <td dir="auto">{formatValidationValue(row.photos)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  )
}

const FILTERS: ValidationAlbumFilter[] = [
  'all',
  'issues',
  'matched',
  'only_remote',
  'only_photos',
]

function filterLabel(filter: ValidationAlbumFilter): string {
  switch (filter) {
    case 'all':
      return t.validationFilterAll
    case 'issues':
      return t.validationFilterIssues
    case 'matched':
      return t.validationMatchedHeading
    case 'only_remote':
      return t.validationOnlyRemoteHeading
    case 'only_photos':
      return t.validationOnlyPhotosHeading
  }
}

export function ValidationReportView({ report }: { report: Report }) {
  const summary = report.summary ?? {}
  const entries = useMemo(() => buildValidationAlbumEntries(report), [report])
  const [filter, setFilter] = useState<ValidationAlbumFilter>(
    report.identical ? 'all' : 'issues',
  )
  const [query, setQuery] = useState('')
  const [selectedKey, setSelectedKey] = useState<string | null>(() =>
    defaultValidationAlbumKey(entries),
  )

  const visible = useMemo(
    () => filterValidationAlbums(entries, filter, query),
    [entries, filter, query],
  )

  useEffect(() => {
    if (selectedKey && visible.some((entry) => entry.key === selectedKey)) {
      return
    }
    setSelectedKey(defaultValidationAlbumKey(visible))
  }, [visible, selectedKey])

  const selected = visible.find((entry) => entry.key === selectedKey) ?? null

  return (
    <div className="validation-report">
      <div className="validation-report__top">
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
        {report.root_url ? (
          <p className="validation-report__root" dir="ltr">
            <a href={report.root_url} target="_blank" rel="noreferrer">
              {report.root_url}
            </a>
          </p>
        ) : null}
        {report.warnings && report.warnings.length > 0 ? (
          <details className="validation-report__warnings">
            <summary>{t.validationWarningsHeading(report.warnings.length)}</summary>
            <ul>
              {report.warnings.map((warning) => (
                <li key={warning} dir="auto">
                  {warning}
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>

      <div className="validation-report__toolbar">
        <div className="validation-report__filters" role="tablist" aria-label={t.validationFilterAria}>
          {FILTERS.map((value) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={filter === value}
              className={[
                'validation-report__filter',
                filter === value ? 'validation-report__filter--active' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              onClick={() => setFilter(value)}
            >
              {filterLabel(value)}
            </button>
          ))}
        </div>
        <label className="validation-report__search-label">
          <span className="visually-hidden">{t.validationSearchLabel}</span>
          <input
            className="validation-report__search"
            type="search"
            value={query}
            placeholder={t.validationSearchPlaceholder}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </div>

      <div className="validation-report__desk">
        <nav className="validation-report__list" aria-label={t.validationAlbumListAria}>
          {visible.length === 0 ? (
            <p className="validation-report__empty-note">{t.validationNoAlbumsFiltered}</p>
          ) : (
            <ul className="validation-report__album-list">
              {visible.map((entry) => (
                <li key={entry.key}>
                  <AlbumListButton
                    entry={entry}
                    selected={entry.key === selected?.key}
                    onSelect={setSelectedKey}
                  />
                </li>
              ))}
            </ul>
          )}
        </nav>
        <div className="validation-report__pane" aria-live="polite">
          {selected ? (
            <AlbumDetail entry={selected} />
          ) : (
            <p className="validation-report__empty-note">{t.validationSelectAlbum}</p>
          )}
        </div>
      </div>
    </div>
  )
}

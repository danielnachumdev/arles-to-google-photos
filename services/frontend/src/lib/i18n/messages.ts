export const APP_LANGUAGES = ['he', 'en'] as const

export type AppLanguage = (typeof APP_LANGUAGES)[number]

export type TextDirection = 'rtl' | 'ltr'

export type MessageCatalog = {
  documentTitle: string
  albumDocumentTitle: (name: string) => string
  kicker: string
  appTitle: string
  lede: string

  navAria: string
  navHome: string
  navAlbums: string
  navJobs: string
  navSettings: string
  openAlbumLibrary: string
  backToAlbums: string
  backToJobs: string
  loadingAlbum: string
  loadingJob: string
  loadingAlbums: string
  loadingJobs: string
  loadingSettings: string

  notFoundHeading: string
  notFoundLede: string
  notFoundHome: string

  libraryHeading: string
  libraryLede: string
  libraryNoMatches: string
  searchLabel: string
  searchPlaceholder: string

  historyEmpty: string
  historyPhotoCount: (n: number) => string
  untitledAlbum: string
  historyOpenAria: (title: string) => string
  deleteAlbum: string
  deleting: string
  confirmDeleteAlbumTitle: string
  confirmDeleteAlbumServer: string
  confirmDeleteAlbumLocal: string
  confirmDeleteAlbumPhotos: string
  confirmCancel: string
  errorDelete: (detail: string) => string
  reprocess: string
  reprocessing: string
  confirmReprocess: string
  confirmReprocessWeb: string
  confirmReprocessConflictTitle: string
  confirmReprocessConflictBody: string
  confirmReprocessConflictUnsaved: string
  confirmReprocessConflictSaved: string
  confirmReprocessConflictWeb: string
  confirmReprocessOverwrite: string
  confirmReprocessCreateNew: string
  confirmReprocessPrefixLabel: string
  reprocessTitlePrefix: string
  confirmOverwriteAlbumTitle: (title: string) => string
  confirmOverwriteAlbumBody: string
  confirmOverwriteAlbumYes: string
  openExistingAlbum: string
  errorOverwrite: (detail: string) => string
  errorReprocess: (detail: string) => string
  errorHistory: (detail: string) => string
  errorJob: (detail: string) => string

  jobsHeading: string
  jobsLede: string
  jobsEmpty: string
  jobsNoMatches: string
  jobsSearchLabel: string
  jobsSearchPlaceholder: string
  jobsOpenAria: (title: string) => string
  jobsColNumber: string
  jobsColId: string
  jobsColType: string
  jobsColStatus: string
  jobsColStart: string
  jobsColEnd: string
  jobsColDuration: string
  jobsColError: string
  jobDetailHeading: string
  jobDocumentTitle: (name: string) => string
  runHistoryHeading: string
  runHistoryEmpty: string
  technicalLogs: string
  jobLogLifecycle: (stage: string) => string
  etaLeft: (seconds: number) => string
  viewJob: string
  openAlbum: string
  jobIdLabel: string
  jobNumberLabel: string
  jobCreatedLabel: string
  jobUpdatedLabel: string
  jobFinishedLabel: string
  jobFolderLabel: string
  jobUrlLabel: string
  jobParentLabel: string
  jobSourceLabel: string
  jobHeadersLabel: string
  jobPreviewSummary: string
  jobChildrenHeading: string
  jobChildrenEmpty: string
  jobStatusHeading: string
  jobTypeHeading: string
  jobErrorHeading: string
  jobWarningsHeading: string
  statusPending: string
  statusRunning: string
  statusWaiting: string
  statusDone: string
  statusFailed: string
  statusCancelled: string
  cancelJob: string
  cancelling: string
  confirmCancelJobTitle: string
  confirmCancelJobBody: string
  confirmCancelJobWithChildrenBody: string
  confirmCancelJobYes: string
  errorCancel: (detail: string) => string
  restartJob: string
  restarting: string
  confirmRestartJobTitle: string
  confirmRestartJobBody: string
  confirmRestartJobWithChildrenBody: string
  confirmRestartJobYes: string
  confirmRestartJobAll: string
  confirmRestartJobRemaining: string
  confirmRestartJobRemainingHeading: string
  confirmRestartJobDoneHeading: string
  errorRestart: (detail: string) => string
  archiveJob: string
  archiving: string
  confirmArchiveJobTitle: string
  confirmArchiveJobBody: string
  confirmArchiveJobYes: string
  errorArchive: (detail: string) => string
  typePreview: string
  typeUpload: string
  typeScrape: string

  importModeAria: string
  importModeUpload: string
  importModeWeb: string
  autoPublishLabel: string
  autoPublishHint: string
  jobAutoPublishLabel: string
  webImportHeading: string
  webUrlLabel: string
  webUrlHint: string
  webInvite: string
  cacheHeadersLabel: string
  cacheHeadersHint: string
  webHeadersHeading: string
  webHeadersHint: string
  headerNameLabel: string
  headerValueLabel: string
  addHeader: string
  removeHeader: string
  startWebImport: string
  importingWeb: string
  errorScrape: (detail: string) => string
  errorScrapeUnsupported: (url: string | null) => string
  errorScrapeFetch: (url: string | null, status?: string | number | null) => string
  errorScrapeEmpty: (url: string | null) => string
  errorInterrupted: string

  folderHeading: string
  folderPickPlaceholder: string
  folderRequiredPrefix: string
  folderRequiredPaths: string
  folderInvite: string
  preparePreview: string
  preparing: string
  fileCount: (n: number) => string

  sendingFiles: (n: number) => string
  sendingFilesProgress: (n: number, percent: number) => string
  storingFiles: string
  storingFilesProgress: (current: number, total: number, percent: number) => string
  uploadProgressLabel: (percent: number, loaded: string, total: string) => string
  previewReady: string
  saved: string
  signingInGoogle: string
  signInCancelled: string
  publishingStatus: string
  publishedStatus: string
  publishedNoUrl: string
  errorPreview: (detail: string) => string
  errorSave: (detail: string) => string
  errorPublish: (detail: string) => string
  errorPayloadTooLarge: string
  errorUnauthorized: string
  errorAuthNotConfigured: string
  errorNetwork: string
  errorHttpFallback: (status: number, detail: string) => string
  jobLabel: string

  albumHeading: string
  structureFallbackWarning: string
  titleLabel: string
  titleHintBefore: string
  titleSelector: string
  titleHintAfter: string
  galleryDescriptionLabel: string
  galleryDescriptionHintBefore: string
  galleryDescriptionSelector: string
  galleryDescriptionHintAfter: string
  journalKicker: string
  journalHintBefore: string
  journalHintFile: string
  journalHeadingLabel: string
  journalBodyLabel: string
  photosHeading: string
  imageTitleHintBefore: string
  imageTitleSelector: string
  imageTitleHintAfter: string
  multiIndex: string

  openPhotosAlbum: string
  save: string
  saving: string
  publish: string
  publishing: string
  published: string
  alreadyRunning: string
  reupload: string

  descriptionLabel: string
  videoDescriptionLabel: string
  dateMismatchBefore: string
  dateMismatchJoin: string
  dateMismatchAfter: string
  fieldTakenOn: string
  fieldRelpath: string
  fieldMtime: string
  fieldSize: string
  missingValue: string
  sizeUnit: string
  openPreviewAria: (id: string) => string
  openVideoPreviewAria: (id: string) => string
  videoPreviewAria: (id: string) => string
  videoBadge: string
  videoPreviewUnavailable: string

  close: string
  toastDismissAria: string
  toastOpenRun: string
  toastOpenAlbum: string
  toastRunSubmitted: (jobLabel: string) => string
  toastPreviewDone: (jobLabel: string) => string
  toastUploadDone: (jobLabel: string) => string
  toastScrapeDone: (jobLabel: string) => string
  toastPreviewFailed: (jobLabel: string, detail: string) => string
  toastUploadFailed: (jobLabel: string, detail: string) => string
  toastScrapeFailed: (jobLabel: string, detail: string) => string
  toastRunCancelled: string
  toastRunCancelledJob: (jobLabel: string) => string

  modified: string
  modifiedAria: string
  discardChanges: string
  discardStay: string
  discardLeave: string

  settingsHeading: string
  settingsLede: string
  languageLabel: string
  appearanceLabel: string
  appearanceHint: string
  appearanceLight: string
  appearanceDark: string
  settingsDefaultImportModeHeading: string
  settingsDefaultImportModeHint: string
  settingsClearCookies: string
  settingsClearCookiesHint: string
  settingsSignOutGoogle: string
  settingsSignOutGoogleHint: string
  settingsOrchestratorHeading: string
  settingsMaxConcurrentLabel: string
  settingsMaxConcurrentHint: string
  settingsMaxConcurrentInfoAria: string
  settingsMaxConcurrentTooltip: string
  settingsOrchestratorSaved: string
  settingsOrchestratorError: (detail: string) => string
  settingsVersionHeading: string
  settingsVersionHint: string
  settingsVersionValue: (version: string) => string
  appVersionLabel: (version: string) => string
  jobsQueueSummary: (running: number, pending: number, waiting: number, max: number) => string
}

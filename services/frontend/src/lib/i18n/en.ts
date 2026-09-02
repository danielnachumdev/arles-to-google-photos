import type { MessageCatalog } from './messages.ts'

export const en: MessageCatalog = {
  documentTitle: 'Arles Migrator',
  albumDocumentTitle: (name) => `${name} · Arles Migrator`,
  kicker: 'From Arles export to Google Photos',
  appTitle: 'Arles Migrator',
  lede: 'Start a new import here: paste an Arles gallery URL, or upload an exported album folder. Review title, journal, and captions, then publish. Saved albums are galleries already in this app; Jobs lists every run.',

  navAria: 'Main navigation',
  navHome: 'New',
  navAlbums: 'Saved albums',
  navJobs: 'Jobs',
  navSettings: 'Settings',
  openAlbumLibrary: 'Open saved albums',
  backToAlbums: 'Back to saved albums',
  backToJobs: 'Back to all jobs',
  loadingAlbum: 'Loading album…',
  loadingJob: 'Loading job…',
  loadingAlbums: 'Loading saved albums…',
  loadingJobs: 'Loading jobs…',
  loadingSettings: 'Loading settings…',

  notFoundHeading: 'Page not found',
  notFoundLede:
    'This link may be invalid, or you may not have access to this page.',
  notFoundHome: 'Back to home',

  libraryHeading: 'Saved albums',
  libraryLede:
    'Galleries already imported into this app (web scrape or folder upload). One row per gallery title — not the live website, and not the Jobs list.',
  libraryNoMatches: 'No albums match this search.',
  searchLabel: 'Search albums',
  searchPlaceholder: 'Gallery title, folder, id, operation, or status',

  historyEmpty:
    'No saved albums yet. After a preview (web import or folder) they stay here across restarts. This is not the live website album list.',
  historyPhotoCount: (n) => (n === 1 ? '1 photo' : `${n} photos`),
  untitledAlbum: 'Untitled album',
  historyOpenAria: (title) => `Open ${title}`,
  deleteAlbum: 'Delete',
  deleting: 'Deleting…',
  confirmDeleteAlbumTitle: 'Delete this album from history?',
  confirmDeleteAlbumServer: 'Only the stored job data on the server (backend) is deleted.',
  confirmDeleteAlbumLocal: 'The local album folder on your computer is not deleted or changed.',
  confirmDeleteAlbumPhotos: 'The Google Photos album and its photos are not deleted or changed.',
  confirmCancel: 'Cancel',
  errorDelete: (detail) => `Delete did not complete. ${detail}`,
  reprocess: 'Reprocess',
  reprocessing: 'Reprocessing…',
  confirmReprocess:
    'Reprocess this album from the stored files? Current edits will be replaced with the new preview.',
  confirmReprocessWeb:
    'Reprocess this web album? This will download all photos, pages, and descriptions from the original URL again and replace the stored preview and edits.',
  confirmReprocessConflictTitle: 'Replace manual changes?',
  confirmReprocessConflictBody:
    'Reprocess would replace your manual album changes on this album.',
  confirmReprocessConflictUnsaved: 'You have unsaved edits in the form.',
  confirmReprocessConflictSaved: 'This album has saved preview edits.',
  confirmReprocessConflictWeb:
    'A web reprocess will also download photos and pages from the original URL again.',
  confirmReprocessOverwrite: 'Overwrite',
  confirmReprocessCreateNew: 'Create new album',
  confirmReprocessPrefixLabel: 'Title prefix',
  reprocessTitlePrefix: 'Reprocessed · ',
  confirmOverwriteAlbumTitle: (title) => `${title} already exists`,
  confirmOverwriteAlbumBody:
    'A stored server job already uses this gallery title. Overwrite will replace the preview and files on the backend. The Google Photos album is not changed and is not republished.',
  confirmOverwriteAlbumYes: 'Yes',
  openExistingAlbum: 'Open existing album',
  errorOverwrite: (detail) => `Overwrite did not complete. ${detail}`,
  errorReprocess: (detail) => `Reprocess did not complete. ${detail}`,
  errorHistory: (detail) => `Could not load the saved album. ${detail}`,
  errorJob: (detail) => `Could not load the job. ${detail}`,

  jobsHeading: 'Jobs',
  jobsLede:
    'Every run on this server: web scrape, folder import, preview, and publish. Not a second album catalog.',
  jobsEmpty: 'No jobs yet.',
  jobsNoMatches: 'No jobs match this search.',
  jobsSearchLabel: 'Search jobs',
  jobsSearchPlaceholder: 'Id, number, operation, status, URL, or folder',
  jobsOpenAria: (title) => `Open job ${title}`,
  jobsColNumber: '#',
  jobsColId: 'Id',
  jobsColType: 'Operation',
  jobsColStatus: 'Status',
  jobsColStart: 'Start',
  jobsColEnd: 'End',
  jobsColDuration: 'Duration',
  jobsColError: 'Error',
  jobDetailHeading: 'Job',
  jobDocumentTitle: (name) => `${name} · Job · Arles Migrator`,
  runHistoryHeading: 'Logs',
  runHistoryEmpty: 'No log lines yet.',
  technicalLogs: 'Technical logs',
  jobLogLifecycle: (stage) => {
    if (stage === 'preview_ready') {
      return 'Preview ready'
    }
    if (stage === 'done') {
      return 'Done'
    }
    if (stage === 'waiting') {
      return 'Waiting'
    }
    if (stage === 'cancelled') {
      return 'Cancelled'
    }
    if (stage === 'error' || stage === 'failed') {
      return 'Error'
    }
    if (stage === 'child') {
      return 'Child job'
    }
    return stage
  },
  etaLeft: (seconds) => {
    const total = Math.max(1, Math.round(seconds))
    if (total < 60) {
      return `~${total}s left`
    }
    const hours = Math.floor(total / 3600)
    const minutes = Math.floor((total % 3600) / 60)
    const secs = total % 60
    if (hours > 0) {
      return minutes > 0 ? `~${hours}h ${minutes}m left` : `~${hours}h left`
    }
    return secs > 0 ? `~${minutes}m ${secs}s left` : `~${minutes}m left`
  },
  viewJob: 'View job',
  openAlbum: 'Open album',
  jobIdLabel: 'Id',
  jobNumberLabel: 'Number',
  jobCreatedLabel: 'Created',
  jobUpdatedLabel: 'Updated',
  jobFinishedLabel: 'Finished',
  jobFolderLabel: 'Folder',
  jobUrlLabel: 'URL',
  jobParentLabel: 'Parent',
  jobSourceLabel: 'Source job',
  jobHeadersLabel: 'Headers',
  jobPreviewSummary: 'Preview',
  jobChildrenHeading: 'Child jobs',
  jobChildrenEmpty: 'No child jobs.',
  jobStatusHeading: 'Status',
  jobTypeHeading: 'Operation',
  jobErrorHeading: 'Error',
  jobWarningsHeading: 'Warnings',
  statusPending: 'Pending',
  statusRunning: 'Running',
  statusWaiting: 'Waiting',
  statusDone: 'Done',
  statusFailed: 'Failed',
  statusCancelled: 'Cancelled',
  cancelJob: 'Cancel',
  cancelling: 'Cancelling…',
  confirmCancelJobTitle: 'Cancel this run?',
  confirmCancelJobBody:
    'In-progress work will stop. Files already saved are kept. This does not delete the job.',
  confirmCancelJobWithChildrenBody:
    'Cancelling this run will also cancel the following jobs:',
  confirmCancelJobYes: 'Cancel run',
  errorCancel: (detail) => `Cancel failed. ${detail}`,
  restartJob: 'Restart',
  restarting: 'Restarting…',
  confirmRestartJobTitle: 'Restart this run?',
  confirmRestartJobBody:
    'Start a new run from scratch? The cancelled job stays in history.',
  confirmRestartJobWithChildrenBody:
    'Some child jobs already finished. Restart everything, or only remaining and failed children? The cancelled run stays in history.',
  confirmRestartJobYes: 'Start new run',
  confirmRestartJobAll: 'Restart all',
  confirmRestartJobRemaining: 'Only remaining / failed',
  confirmRestartJobRemainingHeading: 'Remaining / failed',
  confirmRestartJobDoneHeading: 'Already finished',
  errorRestart: (detail) => `Restart failed. ${detail}`,
  archiveJob: 'Hide',
  archiving: 'Hiding…',
  confirmArchiveJobTitle: 'Hide this run from the list?',
  confirmArchiveJobBody:
    'This run will disappear from Jobs and Saved albums. Files and metadata stay on the server. Child runs are hidden too.',
  confirmArchiveJobYes: 'Hide run',
  errorArchive: (detail) => `Hide failed. ${detail}`,
  typePreview: 'Prepare preview',
  typeUpload: 'Publish to Photos',
  typeScrape: 'Web import',

  importModeAria: 'Import source',
  importModeUpload: 'Upload an exported album folder',
  importModeWeb: 'Import from web',
  autoPublishLabel: 'Auto-publish to Photos',
  autoPublishHint:
    'Sign in to Google Photos if needed. Publish begins after preview is ready.',
  jobAutoPublishLabel: 'Auto-publish',
  webImportHeading: 'Import from web',
  webUrlLabel: 'Gallery URL',
  webUrlHint: 'Start page of an existing Arles HTML gallery.',
  webInvite: 'Enter the gallery URL, then import.',
  cacheHeadersLabel: 'Cache headers for next import',
  cacheHeadersHint: 'Save the headers you used in cookies.',
  webHeadersHeading: 'Extra headers',
  webHeadersHint: 'Optional. Cookie or other headers if needed.',
  headerNameLabel: 'Name',
  headerValueLabel: 'Value',
  addHeader: 'Add header',
  removeHeader: 'Remove',
  startWebImport: 'Import',
  importingWeb: 'Importing…',
  errorScrape: (detail) =>
    `Could not import from the web. Check the URL and headers, then try again. ${detail}`,
  errorScrapeUnsupported: (url) =>
    url
      ? `This URL is not a supported Arles album: ${url}. The importer only works with Arles HTML gallery exports (index.html with a photo grid or album list).`
      : 'This URL is not a supported Arles album. The importer only works with Arles HTML gallery exports (index.html with a photo grid or album list).',
  errorScrapeFetch: (url, status) => {
    const http = status != null && String(status).trim() !== '' ? ` (HTTP ${status})` : ''
    const where = url ? `: ${url}` : ''
    return `Could not download this gallery${http}${where}. Check the URL and any required headers, then try again.`
  },
  errorScrapeEmpty: (url) =>
    url
      ? `No album photos or child galleries were found at this URL: ${url}.`
      : 'No album photos or child galleries were found at this URL.',
  errorInterrupted:
    'This run was interrupted when the server restarted. Restart the job to try again.',

  folderHeading: 'Upload folder',
  folderPickPlaceholder: 'Choose album folder',
  folderRequiredPrefix: 'Required:',
  folderRequiredPaths: 'index.html, hrimages/, imagepages/',
  folderInvite: 'Or upload an exported album folder, then prepare preview.',
  preparePreview: 'Prepare preview',
  preparing: 'Preparing…',
  fileCount: (n) => (n === 1 ? '1 file' : `${n} files`),

  sendingFiles: (n) => `Sending ${n} files…`,
  uploadProgressLabel: (percent, loaded, total) =>
    total ? `${percent}% · ${loaded} / ${total}` : `${percent}%`,
  previewReady: 'Preview is ready.',
  saved: 'Saved.',
  signingInGoogle: 'Signing in to Google Photos…',
  signInCancelled: 'Google sign-in was cancelled.',
  publishingStatus: 'Publishing…',
  publishedStatus: 'Published.',
  publishedNoUrl: 'Published (no album link).',
  errorPreview: (detail) =>
    `Could not build the preview. Make sure the folder contains index.html and hrimages/, then try prepare preview again. ${detail}`,
  errorSave: (detail) => `Save did not complete. Check the connection and try saving again. ${detail}`,
  errorPublish: (detail) =>
    `Publish did not complete. Save your edits, then try publishing again. ${detail}`,
  errorPayloadTooLarge:
    'This album upload was rejected as too large. Import via web URL instead, or try a smaller folder.',
  errorUnauthorized: 'Google Photos authorization failed. Sign in again and retry.',
  errorAuthNotConfigured:
    'Google Photos sign-in is not configured on the server. Add OAuth client settings and try again.',
  errorNetwork: 'Network error. Check your connection and try again.',
  errorHttpFallback: (status, detail) =>
    status > 0 ? (detail ? `HTTP ${status}: ${detail}` : `HTTP ${status}`) : detail || 'Something went wrong.',
  jobLabel: 'Job',

  albumHeading: 'Album',
  structureFallbackWarning:
    'This folder is not a standard Arles album layout. Photos and videos were imported by filename only — gallery title, description, journal, and image captions from HTML may be missing.',
  titleLabel: 'Gallery title',
  titleHintBefore: 'From',
  titleSelector: '.gallerytitle',
  titleHintAfter: '.',
  galleryDescriptionLabel: 'Gallery description',
  galleryDescriptionHintBefore: 'From',
  galleryDescriptionSelector: '.gallerydesc',
  galleryDescriptionHintAfter: '. Leave empty if the album has none.',
  journalKicker: 'Journal',
  journalHintBefore: 'Word HTML at the bottom of',
  journalHintFile: 'index.html',
  journalHeadingLabel: 'Journal heading',
  journalBodyLabel: 'Journal',
  photosHeading: 'Photos',
  imageTitleHintBefore: 'From',
  imageTitleSelector: '.imagetitle',
  imageTitleHintAfter: ' on each image page.',
  multiIndex: 'multi-index',

  openPhotosAlbum: 'Open album in Google Photos',
  save: 'Save',
  saving: 'Saving…',
  publish: 'Publish',
  publishing: 'Publishing…',
  published: 'Published',
  alreadyRunning: 'Already running',
  reupload: 'Publish again',

  descriptionLabel: 'Image title',
  videoDescriptionLabel: 'Video title',
  dateMismatchBefore: 'The dates in ',
  dateMismatchJoin: ' and ',
  dateMismatchAfter: ' differ',
  fieldTakenOn: 'taken_on',
  fieldRelpath: 'relpath',
  fieldMtime: 'mtime',
  fieldSize: 'size',
  missingValue: '—',
  sizeUnit: 'B',
  openPreviewAria: (id) => `Preview ${id}`,
  openVideoPreviewAria: (id) => `Preview video ${id}`,
  videoPreviewAria: (id) => `Video preview ${id}`,
  videoBadge: 'Video',
  videoPreviewUnavailable: 'This video cannot be played in the browser yet.',

  close: 'Close',
  toastDismissAria: 'Dismiss notification',
  toastOpenRun: 'Open run',
  toastOpenAlbum: 'View album on Google',
  toastRunSubmitted: (jobLabel) => `Run started. ${jobLabel}`,
  toastPreviewDone: (jobLabel) => `Preview is ready. ${jobLabel}`,
  toastUploadDone: (jobLabel) => `Upload finished. ${jobLabel}`,
  toastScrapeDone: (jobLabel) => `Web import finished. ${jobLabel}`,
  toastPreviewFailed: (jobLabel, detail) =>
    detail ? `Preview failed. ${jobLabel}. ${detail}` : `Preview failed. ${jobLabel}`,
  toastUploadFailed: (jobLabel, detail) =>
    detail ? `Upload failed. ${jobLabel}. ${detail}` : `Upload failed. ${jobLabel}`,
  toastScrapeFailed: (jobLabel, detail) =>
    detail ? `Web import failed. ${jobLabel}. ${detail}` : `Web import failed. ${jobLabel}`,
  toastRunCancelled: 'Run cancelled.',
  toastRunCancelledJob: (jobLabel) => `Run cancelled. ${jobLabel}`,

  modified: 'Modified',
  modifiedAria: 'This field was modified',
  discardChanges: 'Are you sure you want to discard current changes?',
  discardStay: 'Keep editing',
  discardLeave: 'Discard',

  settingsHeading: 'Settings',
  settingsLede:
    'Choose language and the job queue. Save to apply. Appearance and default import source apply immediately.',
  languageLabel: 'Interface language',
  appearanceLabel: 'Appearance',
  appearanceHint: 'Applies immediately on this device.',
  appearanceLight: 'Light',
  appearanceDark: 'Dark',
  settingsDefaultImportModeHeading: 'Default import source',
  settingsDefaultImportModeHint:
    'Which import method the New album desk opens with. Applies immediately on this device.',
  settingsClearCookies: 'Clear saved cookies',
  settingsClearCookiesHint: 'Removes cached import headers.',
  settingsSignOutGoogle: 'Sign out of Google Photos',
  settingsSignOutGoogleHint:
    'Clears the saved Photos sign-in on this browser. The next publish will ask you to sign in again.',
  settingsOrchestratorHeading: 'Job queue',
  settingsMaxConcurrentLabel: 'Max concurrent jobs',
  settingsMaxConcurrentHint:
    'Only this many jobs run at once. Extra jobs stay pending and still appear in the jobs list.',
  settingsMaxConcurrentInfoAria: 'How the concurrent job limit works',
  settingsMaxConcurrentTooltip:
    'Only running jobs count. Waiting parents (a hub waiting on children) do not. Children share the global pool with other jobs. Raising the limit starts pending jobs immediately. Lowering it does not stop jobs that are already running; new ones wait until a slot frees.',
  settingsOrchestratorSaved: 'Settings saved.',
  settingsOrchestratorError: (detail) => (detail ? `Could not save queue limit. ${detail}` : 'Could not save queue limit.'),
  settingsVersionHeading: 'App version',
  settingsVersionHint: 'Build currently served by this server.',
  settingsVersionValue: (version) => `v${version}`,
  appVersionLabel: (version) => `Version ${version}`,
  jobsQueueSummary: (running, pending, waiting, max) =>
    `${running} running · ${pending} pending · ${waiting} waiting · max ${max}`,
}

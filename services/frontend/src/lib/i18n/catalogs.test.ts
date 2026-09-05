import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { AppCatalogContract } from '../../testing/index.ts'
import { messages } from './catalogs.ts'
import { APP_LANGUAGES } from './messages.ts'
import { messages as barrelMessages } from '../language.ts'
import { setAppLanguage } from './store.ts'

describe('i18n catalogs', () => {
  const contract = new AppCatalogContract()

  beforeEach(() => {
    setAppLanguage('he', false)
  })

  afterEach(() => {
    setAppLanguage('he', false)
  })

  it('registers every AppLanguage with the same MessageCatalog keys', () => {
    contract.assertRegisteredLanguages([...APP_LANGUAGES])
    contract.assertMinKeyCount(50)
    expect(contract.he().navSettings).toBe(messages.he.navSettings)
    expect(contract.en().navSettings).toBe(messages.en.navSettings)
  })

  it('keeps Hebrew and English copy for shared UI keys', () => {
    expect(messages.he.navSettings).toBe('הגדרות')
    expect(messages.en.navSettings).toBe('Settings')
    expect(messages.en.notFoundHeading).toBe('Page not found')
    expect(messages.he.notFoundHeading).toBe('העמוד לא נמצא')
    expect(messages.en.notFoundHome).toBe('Back to home')
    expect(messages.he.notFoundHome).toBe('חזרה לדף הבית')
    expect(messages.he.documentTitle).toBe('מיגרטור Arles')
    expect(messages.en.documentTitle).toBe('Arles Migrator')
    expect(messages.he.navAlbums).toBe('אלבומים שמורים')
    expect(messages.en.navAlbums).toBe('Saved albums')
    expect(messages.he.jobsColNumber).toBe('מספר')
    expect(messages.en.jobsColNumber).toBe('#')
    expect(messages.he.jobsColEnd).toBe('סיום')
    expect(messages.en.jobsColEnd).toBe('End')
    expect(messages.he.jobNumberLabel).toBe('מספר')
    expect(messages.en.jobNumberLabel).toBe('Number')
    expect(messages.he.statusCancelled).toBe('בוטל')
    expect(messages.en.statusCancelled).toBe('Cancelled')
    expect(messages.he.statusWaiting).toBe('בהמתנה')
    expect(messages.en.statusWaiting).toBe('Waiting')
    expect(messages.he.cancelJob).toBe('בטל')
    expect(messages.en.cancelJob).toBe('Cancel')
    expect(messages.he.archiveJob).toBe('הסתר')
    expect(messages.en.archiveJob).toBe('Hide')
    expect(messages.he.confirmArchiveJobYes).toBe('הסתר הרצה')
    expect(messages.en.confirmArchiveJobYes).toBe('Hide run')
    expect(messages.he.restartJob).toBe('הפעל מחדש')
    expect(messages.en.restartJob).toBe('Restart')
    expect(messages.he.confirmRestartJobBody).toBe(
      'להתחיל הרצה חדשה מההתחלה? ההרצה שבוטלה תישאר בהיסטוריה.',
    )
    expect(messages.en.confirmRestartJobBody).toBe(
      'Start a new run from scratch? The cancelled job stays in history.',
    )
    expect(messages.en.confirmRestartJobWithChildrenBody).toBe(
      'Some child jobs already finished. Restart everything, or only remaining and failed children? The cancelled run stays in history.',
    )
    expect(messages.he.confirmRestartJobWithChildrenBody).toBe(
      'חלק מהעבודות הבנות כבר הסתיימו. להפעיל הכל מחדש, או רק את הנותרות והנכשלות? ההרצה שבוטלה תישאר בהיסטוריה.',
    )
    expect(messages.en.confirmRestartJobAll).toBe('Restart all')
    expect(messages.he.confirmRestartJobAll).toBe('הפעל הכל מחדש')
    expect(messages.en.confirmRestartJobRemaining).toBe('Only remaining / failed')
    expect(messages.he.confirmRestartJobRemaining).toBe('רק נותרות / נכשלות')
    expect(messages.en.confirmCancelJobWithChildrenBody).toBe(
      'Cancelling this run will also cancel the following jobs:',
    )
    expect(messages.he.confirmCancelJobWithChildrenBody).toBe(
      'ביטול ההרצה הזו יבטל גם את כל ההרצות הבאות:',
    )
    expect(messages.en.confirmReprocess).toBe(
      'Reprocess this album from the stored files? Current edits will be replaced with the new preview.',
    )
    expect(messages.he.confirmReprocess).toBe(
      'לעבד מחדש את האלבום מהקבצים השמורים? העריכות הנוכחיות יוחלפו בתצוגה המקדימה החדשה.',
    )
    expect(messages.en.confirmReprocessWeb).toBe(
      'Reprocess this web album? This will download all photos, pages, and descriptions from the original URL again and replace the stored preview and edits.',
    )
    expect(messages.he.confirmReprocessWeb).toBe(
      'לעבד מחדש את האלבום מהרשת? פעולה זו תוריד שוב את כל התמונות, הדפים והתיאורים מהכתובת המקורית ותחליף את התצוגה המקדימה והעריכות השמורות.',
    )
    expect(messages.en.confirmReprocessConflictTitle).toBe('Replace manual changes?')
    expect(messages.he.confirmReprocessConflictTitle).toBe('להחליף שינויים ידניים?')
    expect(messages.en.confirmReprocessOverwrite).toBe('Overwrite')
    expect(messages.he.confirmReprocessOverwrite).toBe('דרוס')
    expect(messages.en.confirmReprocessCreateNew).toBe('Create new album')
    expect(messages.he.confirmReprocessCreateNew).toBe('צור אלבום חדש')
    expect(messages.en.reprocessTitlePrefix).toBe('Reprocessed · ')
    expect(messages.he.reprocessTitlePrefix).toBe('עיבוד מחדש · ')
    expect(messages.he.runHistoryHeading).toBe('לוג')
    expect(messages.en.runHistoryHeading).toBe('Logs')
    expect(messages.he.technicalLogs).toBe('לוג טכני')
    expect(messages.en.technicalLogs).toBe('Technical logs')
    expect(messages.he.jobLogLifecycle('preview_ready')).toBe('התצוגה מוכנה')
    expect(messages.en.jobLogLifecycle('preview_ready')).toBe('Preview ready')
    expect(messages.he.autoPublishLabel).toBe('פרסום אוטומטי ל-Photos')
    expect(messages.en.autoPublishLabel).toBe('Auto-publish to Photos')
    expect(messages.en.settingsSignOutGoogle).toBe('Sign out of Google Photos')
    expect(messages.he.settingsSignOutGoogle).toBe('התנתקות מ-Google Photos')
    expect(messages.he.settingsMaxConcurrentLabel).toBe('מספר עבודות במקביל')
    expect(messages.en.settingsMaxConcurrentLabel).toBe('Max concurrent jobs')
    expect(messages.en.appearanceLabel).toBe('Appearance')
    expect(messages.he.appearanceLabel).toBe('תצוגה')
    expect(messages.en.appearanceLight).toBe('Light')
    expect(messages.he.appearanceLight).toBe('בהיר')
    expect(messages.en.appearanceDark).toBe('Dark')
    expect(messages.he.appearanceDark).toBe('כהה')
    expect(messages.en.appearanceHint).toBe('Applies immediately on this device.')
    expect(messages.he.appearanceHint).toBe('חל מיד במכשיר הזה.')
    expect(messages.en.settingsMaxConcurrentInfoAria).toBe('How the concurrent job limit works')
    expect(messages.he.settingsMaxConcurrentInfoAria).toBe('איך פועלת מגבלת העבודות במקביל')
    expect(messages.en.settingsMaxConcurrentTooltip).toBe(
      'Only running jobs count. Waiting parents (a hub waiting on children) do not. Children share the global pool with other jobs. Raising the limit starts pending jobs immediately. Lowering it does not stop jobs that are already running; new ones wait until a slot frees.',
    )
    expect(messages.he.settingsMaxConcurrentTooltip).toBe(
      'רק עבודות רצות נספרות. הרצות אב בהמתנה (שמחכות להרצות בנות) אינן נספרות. ההרצות הבנות חולקות את המאגר הגלובלי עם עבודות אחרות. העלאת המגבלה מפעילה מיד עבודות ממתינות. הורדתה אינה עוצרת עבודות שכבר רצות; עבודות חדשות ימתינו עד שיתפנה מקום.',
    )
    expect(messages.en.settingsOrchestratorSaved).toBe('Settings saved.')
    expect(messages.en.settingsVersionHeading).toBe('App version')
    expect(messages.he.settingsVersionHeading).toBe('גרסת האפליקציה')
    expect(messages.en.settingsVersionValue('1.0.0')).toBe('v1.0.0')
    expect(messages.he.appVersionLabel('1.0.0')).toBe('גרסה 1.0.0')
    expect(messages.en.jobsQueueSummary(2, 6, 1, 2)).toBe(
      '2 running · 6 pending · 1 waiting · max 2',
    )
    expect(messages.he.jobsQueueSummary(2, 6, 1, 2)).toBe(
      '2 רצות · 6 ממתינות · 1 בהמתנה · מקסימום 2',
    )
    expect(messages.en.descriptionLabel).toBe('Image title')
    expect(messages.he.descriptionLabel).toBe('כותרת תמונה')
    expect(messages.en.videoDescriptionLabel).toBe('Video title')
    expect(messages.he.videoDescriptionLabel).toBe('כותרת וידאו')
    expect(messages.en.openPreviewAria('clip01')).toBe('Preview clip01')
    expect(messages.he.openPreviewAria('clip01')).toBe('תצוגה מקדימה clip01')
    expect(messages.en.openVideoPreviewAria('clip01')).toBe('Preview video clip01')
    expect(messages.he.openVideoPreviewAria('clip01')).toBe('תצוגה מקדימה של וידאו clip01')
    expect(messages.en.videoBadge).toBe('Video')
    expect(messages.he.videoBadge).toBe('וידאו')
    expect(messages.en.videoPreviewUnavailable).toBe(
      'Could not load the video preview. Try again later, or publish — the original file is unchanged.',
    )
    expect(messages.he.videoPreviewUnavailable).toContain('תצוגת הווידאו')
    expect(messages.en.videoPreviewNoBrowserCopy).toMatch(/browser-playable/i)
    expect(messages.he.videoPreviewNoBrowserCopy).toBeTruthy()
    expect(messages.en.videoPreviewLoadFailed).toMatch(/Could not load/i)
    expect(messages.he.videoPreviewLoadFailed).toBeTruthy()
  })

  it('implements interpolators in both catalogs', () => {
    expect(messages.he.historyPhotoCount(1)).toBe('תמונה אחת')
    expect(messages.he.historyPhotoCount(3)).toBe('3 תמונות')
    expect(messages.en.historyPhotoCount(1)).toBe('1 photo')
    expect(messages.en.historyPhotoCount(3)).toBe('3 photos')
    expect(messages.he.albumDocumentTitle('קיץ')).toBe('קיץ · מיגרטור Arles')
    expect(messages.en.albumDocumentTitle('Summer')).toBe('Summer · Arles Migrator')
    expect(messages.he.fileCount(1)).toBe('קובץ אחד')
    expect(messages.en.fileCount(2)).toBe('2 files')
    expect(messages.en.etaLeft(12)).toBe('~12s left')
    expect(messages.en.etaLeft(80)).toBe('~1m 20s left')
    expect(messages.en.etaLeft(120)).toBe('~2m left')
    expect(messages.he.etaLeft(12)).toBe('נותרו ~12 שנ׳')
    expect(messages.he.etaLeft(80)).toBe('נותרו ~1 דק׳ 20 שנ׳')
    expect(messages.en.toastRunSubmitted('#12')).toBe('Run started. #12')
    expect(messages.he.toastRunSubmitted('#12')).toBe('ההרצה התחילה. #12')
    expect(messages.en.toastPreviewDone('#12')).toBe('Preview is ready. #12')
    expect(messages.he.toastPreviewDone('#12')).toBe('התצוגה המקדימה מוכנה. #12')
    expect(messages.en.toastUploadDone('#12')).toBe('Upload finished. #12')
    expect(messages.he.toastUploadDone('#12')).toBe('ההעלאה הושלמה. #12')
    expect(messages.en.toastScrapeDone('#12')).toBe('Web import finished. #12')
    expect(messages.he.toastScrapeDone('#12')).toBe('האיסוף מהרשת הושלם. #12')
    expect(messages.en.toastRunCancelledJob('#12')).toBe('Run cancelled. #12')
    expect(messages.he.toastRunCancelledJob('#12')).toBe('ההרצה בוטלה. #12')
    expect(messages.en.toastPreviewFailed('#12', 'missing index.html')).toBe(
      'Preview failed. #12. missing index.html',
    )
    expect(messages.he.toastUploadFailed('#12', '')).toBe('ההעלאה נכשלה. #12')
  })

  it('re-exports the same map from the language barrel', () => {
    expect(barrelMessages).toBe(messages)
    expect(barrelMessages.en.navSettings).toBe('Settings')
  })

  it('invokes interpolators in both catalogs including edge branches', () => {
    for (const catalog of [contract.he(), contract.en()]) {
      expect(catalog.albumDocumentTitle('X')).toContain('X')
      expect(catalog.historyPhotoCount(1)).toBeTruthy()
      expect(catalog.historyPhotoCount(2)).toBeTruthy()
      expect(catalog.historyOpenAria('T')).toContain('T')
      expect(catalog.errorDelete('e')).toContain('e')
      expect(catalog.confirmOverwriteAlbumTitle('T')).toContain('T')
      expect(catalog.errorOverwrite('e')).toContain('e')
      expect(catalog.errorReprocess('e')).toContain('e')
      expect(catalog.errorHistory('e')).toContain('e')
      expect(catalog.errorJob('e')).toContain('e')
      expect(catalog.jobsOpenAria('id')).toContain('id')
      expect(catalog.jobDocumentTitle('N')).toContain('N')
      expect(catalog.jobLogLifecycle('preview_ready')).toBeTruthy()
      expect(catalog.jobLogLifecycle('done')).toBeTruthy()
      expect(catalog.jobLogLifecycle('waiting')).toBeTruthy()
      expect(catalog.jobLogLifecycle('cancelled')).toBeTruthy()
      expect(catalog.jobLogLifecycle('error')).toBeTruthy()
      expect(catalog.jobLogLifecycle('failed')).toBeTruthy()
      expect(catalog.jobLogLifecycle('child')).toBeTruthy()
      expect(catalog.jobLogLifecycle('other')).toBe('other')
      expect(catalog.etaLeft(12)).toBeTruthy()
      expect(catalog.etaLeft(60)).toBeTruthy()
      expect(catalog.etaLeft(80)).toBeTruthy()
      expect(catalog.etaLeft(120)).toBeTruthy()
      expect(catalog.etaLeft(3600)).toBeTruthy()
      expect(catalog.etaLeft(3661)).toBeTruthy()
      expect(catalog.errorCancel('e')).toContain('e')
      expect(catalog.errorRestart('e')).toContain('e')
      expect(catalog.errorScrape('e')).toContain('e')
      expect(catalog.errorScrapeUnsupported('https://albums.example/x')).toContain(
        'https://albums.example/x',
      )
      expect(catalog.errorScrapeUnsupported(null)).toBeTruthy()
      expect(catalog.errorScrapeFetch('https://albums.example/x', 404)).toContain('404')
      expect(catalog.errorScrapeFetch(null, null)).toBeTruthy()
      expect(catalog.errorScrapeEmpty('https://albums.example/x')).toContain(
        'https://albums.example/x',
      )
      expect(catalog.errorScrapeEmpty(null)).toBeTruthy()
      expect(catalog.errorInterrupted).toBeTruthy()
      expect(catalog.loadingAlbums).toBeTruthy()
      expect(catalog.loadingJobs).toBeTruthy()
      expect(catalog.loadingSettings).toBeTruthy()
      expect(catalog.fileCount(1)).toBeTruthy()
      expect(catalog.fileCount(3)).toBeTruthy()
      expect(catalog.sendingFiles(3)).toContain('3')
      expect(catalog.sendingFilesProgress(3, 42)).toContain('42')
      expect(catalog.storingFiles).toBeTruthy()
      expect(catalog.storingFilesProgress(2, 5, 40)).toContain('2/5')
      expect(catalog.uploadProgressLabel(42, '1 MB', '2 MB')).toContain('42')
      expect(catalog.errorPreview('e')).toContain('e')
      expect(catalog.errorSave('e')).toContain('e')
      expect(catalog.errorPublish('e')).toContain('e')
      expect(catalog.errorPayloadTooLarge).toBeTruthy()
      expect(catalog.errorUnauthorized).toBeTruthy()
      expect(catalog.errorAuthNotConfigured).toBeTruthy()
      expect(catalog.errorNetwork).toBeTruthy()
      expect(catalog.errorHttpFallback(500, 'boom')).toContain('500')
      expect(catalog.errorHttpFallback(500, 'boom')).toContain('boom')
      expect(catalog.errorHttpFallback(502, '')).toContain('502')
      expect(catalog.openPreviewAria('id')).toContain('id')
      expect(catalog.openVideoPreviewAria('id')).toContain('id')
      expect(catalog.videoPreviewAria('id')).toContain('id')
      expect(catalog.toastRunSubmitted('#1')).toContain('#1')
      expect(catalog.toastPreviewDone('#1')).toContain('#1')
      expect(catalog.toastUploadDone('#1')).toContain('#1')
      expect(catalog.toastScrapeDone('#1')).toContain('#1')
      expect(catalog.toastPreviewFailed('#1', 'x')).toContain('x')
      expect(catalog.toastPreviewFailed('#1', '')).toBeTruthy()
      expect(catalog.toastUploadFailed('#1', 'x')).toContain('x')
      expect(catalog.toastUploadFailed('#1', '')).toBeTruthy()
      expect(catalog.toastScrapeFailed('#1', 'x')).toContain('x')
      expect(catalog.toastScrapeFailed('#1', '')).toBeTruthy()
      expect(catalog.toastRunCancelledJob('#1')).toContain('#1')
      expect(catalog.settingsOrchestratorError('e')).toContain('e')
      expect(catalog.settingsOrchestratorError('')).toBeTruthy()
      expect(catalog.jobsQueueSummary(1, 2, 3, 4)).toBeTruthy()
    }
  })
})

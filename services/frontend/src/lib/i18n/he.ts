import type { MessageCatalog } from './messages.ts'

export const he: MessageCatalog = {
  documentTitle: 'מיגרטור Arles',
  albumDocumentTitle: (name) => `${name} · מיגרטור Arles`,
  kicker: 'מייצוא Arles אל Google Photos',
  appTitle: 'מיגרטור Arles',
  lede: 'התחילו ייבוא חדש כאן: הדביקו כתובת גלריית Arles, או העלו תיקיית אלבום מיוצאת. בדקו כותרת, יומן וכותרות תמונה, ואז פרסמו. אלבומים שמורים הם גלריות שכבר באפליקציה; הרצות מציגות כל ריצה.',

  navAria: 'ניווט ראשי',
  navHome: 'חדש',
  navAlbums: 'אלבומים שמורים',
  navJobs: 'הרצות',
  navSettings: 'הגדרות',
  openAlbumLibrary: 'פתיחת אלבומים שמורים',
  backToAlbums: 'חזרה לאלבומים שמורים',
  backToJobs: 'חזרה לכל ההרצות',
  loadingAlbum: 'טוען אלבום…',
  loadingJob: 'טוען הרצה…',
  loadingAlbums: 'טוען אלבומים שמורים…',
  loadingJobs: 'טוען הרצות…',
  loadingSettings: 'טוען הגדרות…',
  loadingThumbnail: 'טוען תמונה ממוזערת…',

  notFoundHeading: 'העמוד לא נמצא',
  notFoundLede: 'ייתכן שהקישור אינו תקין, או שאין לך גישה לעמוד זה.',
  notFoundHome: 'חזרה לדף הבית',

  libraryHeading: 'אלבומים שמורים',
  libraryLede:
    'גלריות שכבר יובאו לאפליקציה (איסוף מהרשת או העלאת תיקייה). שורה אחת לכל כותרת גלריה — לא האתר החי, ולא רשימת ההרצות.',
  libraryNoMatches: 'אין אלבומים שתואמים לחיפוש.',
  searchLabel: 'חיפוש אלבומים',
  searchPlaceholder: 'כותרת הגלריה, תיקייה, מזהה, פעולה או מצב',

  historyEmpty:
    'אין אלבומים שמורים עדיין. אחרי תצוגה מקדימה (ייבוא מהרשת או תיקייה) הם יישארו כאן גם אחרי הפעלה מחדש. זו לא רשימת האלבומים באתר החי.',
  historyPhotoCount: (n) => (n === 1 ? 'תמונה אחת' : `${n} תמונות`),
  untitledAlbum: 'אלבום ללא כותרת',
  historyOpenAria: (title) => `פתיחת ${title}`,
  deleteAlbum: 'מחיקה',
  deleting: 'מוחק…',
  confirmDeleteAlbumTitle: 'למחוק את האלבום מההיסטוריה?',
  confirmDeleteAlbumServer: 'יימחקו רק נתוני המשימה השמורים בשרת (backend).',
  confirmDeleteAlbumLocal: 'תיקיית האלבום במחשב המקומי לא תימחק ולא תשתנה.',
  confirmDeleteAlbumPhotos: 'אלבום Google Photos והתמונות שבו לא יימחקו ולא ישתנו.',
  confirmCancel: 'ביטול',
  errorDelete: (detail) => `המחיקה לא הושלמה. ${detail}`,
  reprocess: 'עיבוד מחדש',
  reprocessing: 'מעבד מחדש…',
  confirmReprocess:
    'לעבד מחדש את האלבום מהקבצים השמורים? העריכות הנוכחיות יוחלפו בתצוגה המקדימה החדשה.',
  confirmReprocessWeb:
    'לעבד מחדש את האלבום מהרשת? פעולה זו תוריד שוב את כל התמונות, הדפים והתיאורים מהכתובת המקורית ותחליף את התצוגה המקדימה והעריכות השמורות.',
  confirmReprocessConflictTitle: 'להחליף שינויים ידניים?',
  confirmReprocessConflictBody: 'עיבוד מחדש יחליף את השינויים הידניים באלבום הזה.',
  confirmReprocessConflictUnsaved: 'יש עריכות שלא נשמרו בטופס.',
  confirmReprocessConflictSaved: 'באלבום הזה יש עריכות שמורות בתצוגה המקדימה.',
  confirmReprocessConflictWeb:
    'עיבוד מחדש מהרשת יוריד שוב גם תמונות ודפים מהכתובת המקורית.',
  confirmReprocessOverwrite: 'דרוס',
  confirmReprocessCreateNew: 'צור אלבום חדש',
  confirmReprocessPrefixLabel: 'קידומת לכותרת',
  reprocessTitlePrefix: 'עיבוד מחדש · ',
  confirmOverwriteAlbumTitle: (title) => `האלבום «${title}» כבר קיים`,
  confirmOverwriteAlbumBody:
    'כבר יש משימה שמורה בשרת עם אותה כותרת גלריה. דריסה תחליף את התצוגה המקדימה והקבצים השמורים בשרת. אלבום Google Photos לא ישתנה ולא יפורסם מחדש.',
  confirmOverwriteAlbumYes: 'כן',
  openExistingAlbum: 'פתח את האלבום הקיים',
  errorOverwrite: (detail) => `הדריסה לא הושלמה. ${detail}`,
  errorReprocess: (detail) => `העיבוד מחדש לא הושלם. ${detail}`,
  errorHistory: (detail) => `לא ניתן לטעון את האלבום השמור. ${detail}`,
  errorJob: (detail) => `לא ניתן לטעון את ההרצה. ${detail}`,

  jobsHeading: 'הרצות',
  jobsLede:
    'כל הרצה בשרת: איסוף מהרשת, ייבוא תיקייה, תצוגה מקדימה ופרסום. זה לא קטלוג אלבומים נוסף.',
  jobsEmpty: 'אין הרצות עדיין.',
  jobsNoMatches: 'אין הרצות שתואמות לחיפוש.',
  jobsSearchLabel: 'חיפוש הרצות',
  jobsSearchPlaceholder: 'מזהה, מספר, פעולה, סטטוס, כתובת או תיקייה',
  jobsOpenAria: (title) => `פתיחת הרצה ${title}`,
  jobsColNumber: 'מספר',
  jobsColId: 'מזהה',
  jobsColType: 'פעולה',
  jobsColStatus: 'סטטוס',
  jobsColStart: 'התחלה',
  jobsColEnd: 'סיום',
  jobsColDuration: 'משך',
  jobsColError: 'שגיאה',
  jobDetailHeading: 'הרצה',
  jobDocumentTitle: (name) => `${name} · הרצה · מיגרטור Arles`,
  runHistoryHeading: 'לוג',
  runHistoryEmpty: 'אין שורות לוג עדיין.',
  technicalLogs: 'לוג טכני',
  jobLogLifecycle: (stage) => {
    if (stage === 'preview_ready') {
      return 'התצוגה מוכנה'
    }
    if (stage === 'done') {
      return 'הושלם'
    }
    if (stage === 'waiting') {
      return 'בהמתנה'
    }
    if (stage === 'cancelled') {
      return 'בוטל'
    }
    if (stage === 'error' || stage === 'failed') {
      return 'שגיאה'
    }
    if (stage === 'child') {
      return 'הרצת בת'
    }
    return stage
  },
  etaLeft: (seconds) => {
    const total = Math.max(1, Math.round(seconds))
    if (total < 60) {
      return `נותרו ~${total} שנ׳`
    }
    const hours = Math.floor(total / 3600)
    const minutes = Math.floor((total % 3600) / 60)
    const secs = total % 60
    if (hours > 0) {
      return minutes > 0 ? `נותרו ~${hours} שע׳ ${minutes} דק׳` : `נותרו ~${hours} שע׳`
    }
    return secs > 0 ? `נותרו ~${minutes} דק׳ ${secs} שנ׳` : `נותרו ~${minutes} דק׳`
  },
  viewJob: 'צפייה בהרצה',
  openAlbum: 'פתיחת אלבום',
  jobIdLabel: 'מזהה',
  jobNumberLabel: 'מספר',
  jobCreatedLabel: 'נוצרה',
  jobUpdatedLabel: 'עודכנה',
  jobFinishedLabel: 'הסתיימה',
  jobFolderLabel: 'תיקייה',
  jobUrlLabel: 'כתובת',
  jobParentLabel: 'הרצת אב',
  jobSourceLabel: 'הרצת מקור',
  jobHeadersLabel: 'כותרות',
  jobPreviewSummary: 'תצוגה מקדימה',
  jobChildrenHeading: 'הרצות בנות',
  jobChildrenEmpty: 'אין הרצות בנות.',
  jobStatusHeading: 'סטטוס',
  jobTypeHeading: 'פעולה',
  jobErrorHeading: 'שגיאה',
  jobWarningsHeading: 'אזהרות',
  statusPending: 'ממתין',
  statusRunning: 'רץ',
  statusWaiting: 'בהמתנה',
  statusDone: 'הסתיים',
  statusFailed: 'נכשל',
  statusCancelled: 'בוטל',
  cancelJob: 'בטל',
  cancelling: 'מבטל…',
  confirmCancelJobTitle: 'לבטל את ההרצה?',
  confirmCancelJobBody: 'העבודה תיעצר. קבצים שכבר נשמרו יישארו. זה לא מוחק את ההרצה.',
  confirmCancelJobWithChildrenBody: 'ביטול ההרצה הזו יבטל גם את כל ההרצות הבאות:',
  confirmCancelJobYes: 'בטל הרצה',
  errorCancel: (detail) => `הביטול נכשל. ${detail}`,
  restartJob: 'הפעל מחדש',
  restarting: 'מפעיל מחדש…',
  confirmRestartJobTitle: 'להפעיל מחדש את ההרצה?',
  confirmRestartJobBody: 'להתחיל הרצה חדשה מההתחלה? ההרצה שבוטלה תישאר בהיסטוריה.',
  confirmRestartJobWithChildrenBody:
    'חלק מהעבודות הבנות כבר הסתיימו. להפעיל הכל מחדש, או רק את הנותרות והנכשלות? ההרצה שבוטלה תישאר בהיסטוריה.',
  confirmRestartJobYes: 'התחל הרצה חדשה',
  confirmRestartJobAll: 'הפעל הכל מחדש',
  confirmRestartJobRemaining: 'רק נותרות / נכשלות',
  confirmRestartJobRemainingHeading: 'נותרות / נכשלות',
  confirmRestartJobDoneHeading: 'כבר הסתיימו',
  errorRestart: (detail) => `ההפעלה מחדש נכשלה. ${detail}`,
  archiveJob: 'הסתר',
  archiving: 'מסתיר…',
  confirmArchiveJobTitle: 'להסתיר את ההרצה?',
  confirmArchiveJobBody:
    'ההרצה תוסר מרשימת ההרצות ומהאלבומים השמורים. הקבצים והנתונים יישארו בשרת. הרצות בנות יוסתרו גם כן.',
  confirmArchiveJobYes: 'הסתר הרצה',
  errorArchive: (detail) => `ההסתרה נכשלה. ${detail}`,
  typePreview: 'הכנת תצוגה',
  typeUpload: 'פרסום ל-Photos',
  typeScrape: 'ייבוא מהרשת',

  importModeAria: 'אופן ייבוא',
  importModeUpload: 'העלאת תיקיית אלבום מיוצאת',
  importModeWeb: 'ייבוא מהרשת',
  autoPublishLabel: 'פרסום אוטומטי ל-Photos',
  autoPublishHint: 'התחברו ל-Google Photos אם צריך. הפרסום יתחיל אחרי שהתצוגה המקדימה מוכנה.',
  jobAutoPublishLabel: 'פרסום אוטומטי',
  webImportHeading: 'ייבוא מהרשת',
  webUrlLabel: 'כתובת הגלריה',
  webUrlHint: 'דף הפתיחה של גלריית Arles קיימת.',
  webInvite: 'הזינו את כתובת הגלריה, ואז ייבוא.',
  cacheHeadersLabel: 'שמירת כותרות לייבוא הבא',
  cacheHeadersHint: 'שומר את הכותרות שבהן השתמשתם בעוגיות.',
  webHeadersHeading: 'כותרות נוספות',
  webHeadersHint: 'אופציונלי. Cookie או כותרות אחרות, אם צריך.',
  headerNameLabel: 'שם',
  headerValueLabel: 'ערך',
  addHeader: 'הוספת כותרת',
  removeHeader: 'הסרה',
  startWebImport: 'ייבוא',
  importingWeb: 'מייבא…',
  errorScrape: (detail) =>
    `לא ניתן לייבא מהרשת. בדקו את הכתובת ואת הכותרות, ואז נסו שוב. ${detail}`,
  errorScrapeUnsupported: (url) =>
    url
      ? `כתובת זו אינה אלבום Arles נתמך: ${url}. הייבוא עובד רק עם ייצוא HTML של Arles (index.html עם רשת תמונות או רשימת אלבומים).`
      : 'כתובת זו אינה אלבום Arles נתמך. הייבוא עובד רק עם ייצוא HTML של Arles (index.html עם רשת תמונות או רשימת אלבומים).',
  errorScrapeFetch: (url, status) => {
    const http = status != null && String(status).trim() !== '' ? ` (HTTP ${status})` : ''
    const where = url ? `: ${url}` : ''
    return `לא ניתן להוריד את הגלריה${http}${where}. בדקו את הכתובת ואת הכותרות הנדרשות, ואז נסו שוב.`
  },
  errorScrapeEmpty: (url) =>
    url
      ? `לא נמצאו תמונות אלבום או גלריות־בן בכתובת זו: ${url}.`
      : 'לא נמצאו תמונות אלבום או גלריות־בן בכתובת זו.',
  errorInterrupted:
    'ההרצה הופסקה כשהשרת הופעל מחדש. הפעילו מחדש את ההרצה כדי לנסות שוב.',

  folderHeading: 'העלאת תיקייה',
  folderPickPlaceholder: 'בחירת תיקיית אלבום',
  folderRequiredPrefix: 'נדרש:',
  folderRequiredPaths: 'index.html, hrimages/, imagepages/',
  folderInvite: 'או העלו תיקיית אלבום מיוצאת, ואז הכנת תצוגה מקדימה.',
  preparePreview: 'התחל',
  preparing: 'מכין…',
  fileCount: (n) => (n === 1 ? 'קובץ אחד' : `${n} קבצים`),

  sendingFiles: (n) => `מעלה ${n} קבצים לשרת…`,
  sendingFilesProgress: (n, percent) => `מעלה ${n} קבצים לשרת… ${percent}%`,
  storingFiles: 'שומר קבצים בשרת…',
  storingFilesProgress: (current, total, percent) =>
    `שומר קבצים בשרת… ${current}/${total} (${percent}%)`,
  uploadProgressLabel: (percent, loaded, total) =>
    total ? `${percent}% · ${loaded} / ${total}` : `${percent}%`,
  previewReady: 'התצוגה המקדימה מוכנה.',
  saved: 'נשמר.',
  signingInGoogle: 'מתחברים ל־Google Photos…',
  signInCancelled: 'ההתחברות ל־Google בוטלה.',
  publishingStatus: 'מפרסם…',
  publishedStatus: 'פורסם.',
  publishedNoUrl: 'פורסם (אין קישור לאלבום).',
  errorPreview: (detail) =>
    `לא ניתן לבנות תצוגה מקדימה. ודאו שבתיקייה יש index.html ו־hrimages/, ואז נסו שוב הכנת תצוגה מקדימה. ${detail}`,
  errorSave: (detail) => `השמירה לא הושלמה. בדקו את החיבור ונסו שוב שמירה. ${detail}`,
  errorPublish: (detail) => `הפרסום לא הושלם. שמרו את העריכות, ואז נסו שוב פרסום. ${detail}`,
  errorPayloadTooLarge:
    'העלאת האלבום נדחתה כי היא גדולה מדי. ייבאו באמצעות כתובת אתר, או נסו תיקייה קטנה יותר.',
  errorUnauthorized: 'ההרשאה ל־Google Photos נכשלה. התחברו שוב ונסו שוב.',
  errorAuthNotConfigured:
    'התחברות ל־Google Photos אינה מוגדרת בשרת. הוסיפו הגדרות OAuth ונסו שוב.',
  errorNetwork: 'שגיאת רשת. בדקו את החיבור ונסו שוב.',
  errorHttpFallback: (status, detail) =>
    status > 0 ? (detail ? `HTTP ${status}: ${detail}` : `HTTP ${status}`) : detail || 'משהו השתבש.',
  jobLabel: 'הרצה',

  albumHeading: 'אלבום',
  structureFallbackWarning:
    'התיקייה אינה בפריסת אלבום Arles רגילה. התמונות והסרטונים יובאו לפי שם קובץ בלבד — כותרת גלריה, תיאור, יומן וכיתובים מ־HTML עלולים להיות חסרים.',
  titleLabel: 'כותרת הגלריה',
  titleHintBefore: 'מתוך',
  titleSelector: '.gallerytitle',
  titleHintAfter: '.',
  galleryDescriptionLabel: 'תיאור הגלריה',
  galleryDescriptionHintBefore: 'מתוך',
  galleryDescriptionSelector: '.gallerydesc',
  galleryDescriptionHintAfter: '. השאירו ריק אם אין באלבום.',
  journalKicker: 'יומן',
  journalHintBefore: 'HTML של Word בתחתית',
  journalHintFile: 'index.html',
  journalHeadingLabel: 'כותרת היומן',
  journalBodyLabel: 'יומן',
  photosHeading: 'תמונות',
  imageTitleHintBefore: 'מתוך',
  imageTitleSelector: '.imagetitle',
  imageTitleHintAfter: ' בכל דף תמונה.',
  multiIndex: 'multi-index',

  openPhotosAlbum: 'פתיחת אלבום ב־Google Photos',
  save: 'שמירה',
  saving: 'שומר…',
  publish: 'פרסום',
  publishing: 'מפרסם…',
  published: 'פורסם',
  alreadyRunning: 'כבר רץ',
  reupload: 'פרסם שוב',

  descriptionLabel: 'כותרת תמונה',
  videoDescriptionLabel: 'כותרת וידאו',
  dateMismatchBefore: 'התאריכים ב־',
  dateMismatchJoin: ' וב־',
  dateMismatchAfter: ' שונים',
  fieldTakenOn: 'taken_on',
  fieldRelpath: 'relpath',
  fieldMtime: 'mtime',
  fieldSize: 'size',
  missingValue: '—',
  sizeUnit: 'B',
  openPreviewAria: (id) => `תצוגה מקדימה ${id}`,
  openVideoPreviewAria: (id) => `תצוגה מקדימה של וידאו ${id}`,
  videoPreviewAria: (id) => `תצוגה מקדימה של וידאו ${id}`,
  videoBadge: 'וידאו',
  videoPreviewNoBrowserCopy:
    'אין תצוגה מקדימה שניתנת לניגון בדפדפן לקובץ זה (לעיתים WMV בלי המרה ל־MP4). הפרסום עדיין מעלה את הקובץ המקורי.',
  videoPreviewLoadFailed:
    'לא ניתן לטעון את תצוגת הווידאו. נסו שוב מאוחר יותר, או פרסמו — הקובץ המקורי לא משתנה.',
  videoPreviewUnavailable:
    'לא ניתן לטעון את תצוגת הווידאו. נסו שוב מאוחר יותר, או פרסמו — הקובץ המקורי לא משתנה.',

  close: 'סגירה',
  toastDismissAria: 'סגירת הודעה',
  toastOpenRun: 'פתח הרצה',
  toastOpenAlbum: 'צפייה באלבום ב-Google',
  toastRunSubmitted: (jobLabel) => `ההרצה התחילה. ${jobLabel}`,
  toastPreviewDone: (jobLabel) => `התצוגה המקדימה מוכנה. ${jobLabel}`,
  toastUploadDone: (jobLabel) => `ההעלאה הושלמה. ${jobLabel}`,
  toastScrapeDone: (jobLabel) => `האיסוף מהרשת הושלם. ${jobLabel}`,
  toastPreviewFailed: (jobLabel, detail) =>
    detail ? `הכנת התצוגה המקדימה נכשלה. ${jobLabel}. ${detail}` : `הכנת התצוגה המקדימה נכשלה. ${jobLabel}`,
  toastUploadFailed: (jobLabel, detail) =>
    detail ? `ההעלאה נכשלה. ${jobLabel}. ${detail}` : `ההעלאה נכשלה. ${jobLabel}`,
  toastScrapeFailed: (jobLabel, detail) =>
    detail ? `האיסוף מהרשת נכשל. ${jobLabel}. ${detail}` : `האיסוף מהרשת נכשל. ${jobLabel}`,
  toastRunCancelled: 'ההרצה בוטלה.',
  toastRunCancelledJob: (jobLabel) => `ההרצה בוטלה. ${jobLabel}`,

  modified: 'שונה',
  modifiedAria: 'שדה זה עודכן',
  discardChanges: 'האם אתם בטוחים שברצונכם לבטל את השינויים הנוכחיים?',
  discardStay: 'המשך בעריכה',
  discardLeave: 'בטל שינויים',

  settingsHeading: 'הגדרות',
  settingsLede: 'בחרו שפה ותור עבודות. שמירה תחיל את השינויים. התצוגה ומקור הייבוא ברירת המחדל חלים מיד.',
  languageLabel: 'שפת ממשק',
  appearanceLabel: 'תצוגה',
  appearanceHint: 'חל מיד במכשיר הזה.',
  appearanceLight: 'בהיר',
  appearanceDark: 'כהה',
  settingsDefaultImportModeHeading: 'מקור ייבוא ברירת מחדל',
  settingsDefaultImportModeHint: 'באיזו שיטת ייבוא נפתח שולחן האלבום החדש. חל מיד במכשיר הזה.',
  settingsClearCookies: 'מחיקת עוגיות שמורות',
  settingsClearCookiesHint: 'מוחק את כותרות הייבוא השמורות.',
  settingsSignOutGoogle: 'התנתקות מ-Google Photos',
  settingsSignOutGoogleHint:
    'מוחק את ההתחברות השמורה ל-Photos בדפדפן זה. בפרסום הבא תתבקשו להתחבר שוב.',
  settingsOrchestratorHeading: 'תור עבודות',
  settingsMaxConcurrentLabel: 'מספר עבודות במקביל',
  settingsMaxConcurrentHint:
    'רק מספר זה של עבודות רצות בבת אחת. השאר ממתינות ומופיעות ברשימת העבודות.',
  settingsMaxConcurrentInfoAria: 'איך פועלת מגבלת העבודות במקביל',
  settingsMaxConcurrentTooltip:
    'רק עבודות רצות נספרות. הרצות אב בהמתנה (שמחכות להרצות בנות) אינן נספרות. ההרצות הבנות חולקות את המאגר הגלובלי עם עבודות אחרות. העלאת המגבלה מפעילה מיד עבודות ממתינות. הורדתה אינה עוצרת עבודות שכבר רצות; עבודות חדשות ימתינו עד שיתפנה מקום.',
  settingsOrchestratorSaved: 'ההגדרות נשמרו.',
  settingsOrchestratorError: (detail) =>
    detail ? `לא ניתן לשמור את מגבלת התור. ${detail}` : 'לא ניתן לשמור את מגבלת התור.',
  settingsVersionHeading: 'גרסת האפליקציה',
  settingsVersionHint: 'הבנייה שמגישה השרת כרגע.',
  settingsVersionValue: (version) => `v${version}`,
  appVersionLabel: (version) => `גרסה ${version}`,
  jobsQueueSummary: (running, pending, waiting, max) =>
    `${running} רצות · ${pending} ממתינות · ${waiting} בהמתנה · מקסימום ${max}`,
}

import { fireEvent, screen, within } from '@testing-library/react'
import { t } from '../lib/language.ts'

/** Shared confirm/cancel flows for in-app dialogs (never window.confirm). */
export abstract class DialogInteractor {
  abstract dialogName(): string | RegExp

  find(): HTMLElement {
    return screen.getByRole('dialog', { name: this.dialogName() })
  }

  query(): HTMLElement | null {
    return screen.queryByRole('dialog', { name: this.dialogName() })
  }

  async wait(): Promise<HTMLElement> {
    return screen.findByRole('dialog', { name: this.dialogName() })
  }

  click(label: string): void {
    fireEvent.click(within(this.find()).getByRole('button', { name: label }))
  }

  confirm(label: string): void {
    this.click(label)
  }

  cancel(label = t.confirmCancel): void {
    this.click(label)
  }

  expectOpen(): HTMLElement {
    const dialog = this.find()
    expect(dialog).toBeInTheDocument()
    return dialog
  }

  expectClosed(): void {
    expect(this.query()).not.toBeInTheDocument()
  }
}

export class ConfirmDialogInteractor extends DialogInteractor {
  private readonly title: string | RegExp

  constructor(title: string | RegExp) {
    super()
    this.title = title
  }

  override dialogName(): string | RegExp {
    return this.title
  }
}

export class ReprocessDialogInteractor extends ConfirmDialogInteractor {
  constructor(web = false) {
    super(web ? t.confirmReprocessWeb : t.confirmReprocess)
  }
}

export class ReprocessConflictInteractor extends ConfirmDialogInteractor {
  constructor() {
    super(t.confirmReprocessConflictTitle)
  }

  overwrite(): void {
    this.click(t.confirmReprocessOverwrite)
  }

  createNew(): void {
    this.click(t.confirmReprocessCreateNew)
  }
}

export class RestartJobDialogInteractor extends ConfirmDialogInteractor {
  constructor() {
    super(t.confirmRestartJobTitle)
  }

  restartAll(): void {
    this.click(t.confirmRestartJobAll)
  }

  restartRemaining(): void {
    this.click(t.confirmRestartJobRemaining)
  }

  restartSimple(): void {
    this.click(t.confirmRestartJobYes)
  }
}

export class CancelJobDialogInteractor extends ConfirmDialogInteractor {
  constructor() {
    super(t.confirmCancelJobTitle)
  }

  confirmCancelJob(): void {
    this.click(t.confirmCancelJobYes)
  }
}

export class DiscardChangesInteractor extends ConfirmDialogInteractor {
  constructor() {
    super(t.discardChanges)
  }

  stay(): void {
    this.click(t.discardStay)
  }

  leave(): void {
    this.click(t.discardLeave)
  }
}

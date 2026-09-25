import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { QueueRow } from './QueueRow'
import type { LibraryItem } from '../../types/domain'

function row(item: LibraryItem) {
  const submit = vi.fn().mockResolvedValue(undefined)
  render(<table><tbody><QueueRow
    item={item} active={false} processingReady setupReason="" busy={false} selected={false}
    onToggleSelection={vi.fn()} onReview={vi.fn()} onArchive={vi.fn()}
    onOpenOutput={vi.fn()} onRetry={vi.fn()} onAuthenticationRequired={vi.fn()}
    onDownloadJavaScriptRuntime={vi.fn()} onSubmit={submit}
    onCancelRunning={vi.fn()} onRemoveQueued={vi.fn()}
  /></tbody></table>)
  return submit
}

describe('source identity in the Queue', () => {
  it('keeps legacy items out of bulk processing and requires explicit retranscription', () => {
    const submit = row({ source: 'C:\\Ready\\film.mkv', status: 'unverified', date_added: '', transcript: null, output: null })
    expect(screen.getByText('Needs review')).toBeInTheDocument()
    expect(screen.getByRole('checkbox')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Censor' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Play' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Archive' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Retranscribe' }))
    expect(submit).toHaveBeenCalledWith('C:\\Ready\\film.mkv', 'report_only', { force_transcribe: true })
  })

  it('describes stored transcript state without claiming a fresh source verification', () => {
    row({ source: 'C:\\Ready\\film.mkv', status: 'transcribed', date_added: '', transcript: 'record.json', output: null })
    expect(screen.getByText('Transcript recorded; source checked when used')).toBeInTheDocument()
  })

  it('offers explicit output replacement after incomplete provenance publication', () => {
    const submit = row({ source: 'C:\\Ready\\film.mkv', status: 'transcribed', date_added: '', transcript: 'record.json', output: 'finished.mkv' })
    expect(screen.queryByRole('button', { name: 'Play' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Recensor' }))
    expect(submit).toHaveBeenCalledWith('C:\\Ready\\film.mkv', 'censor', { overwrite_output: true })
  })
})

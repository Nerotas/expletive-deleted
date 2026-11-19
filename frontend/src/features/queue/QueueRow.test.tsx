import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { QueueRow } from './QueueRow'
import type { Job, JobEvent, LibraryItem } from '../../types/domain'

function row(item: LibraryItem, job?: Job, event?: JobEvent) {
  const submit = vi.fn().mockResolvedValue(undefined)
  render(<table><tbody><QueueRow
    item={item} job={job} event={event} active={false} processingReady setupReason="" busy={false} selected={false}
    onToggleSelection={vi.fn()} onReview={vi.fn()} onArchive={vi.fn()}
    onOpenOutput={vi.fn()} onRetry={vi.fn()} onAuthenticationRequired={vi.fn()}
    onDownloadJavaScriptRuntime={vi.fn()} onSubmit={submit}
    onCancelRunning={vi.fn()} onRemoveQueued={vi.fn()}
  /></tbody></table>)
  return submit
}

describe('source identity in the Queue', () => {
  it('keeps legacy items out of bulk processing and requires explicit retranscription', () => {
    const submit = row({ source: 'C:\\Ready\\film.mkv', status: 'unverified', date_added: '', transcript: null, output: null, duration_seconds: null })
    expect(screen.getByText('Needs review')).toBeInTheDocument()
    expect(screen.getByRole('checkbox')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Censor' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Play' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Archive' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Retranscribe' }))
    expect(submit).toHaveBeenCalledWith('C:\\Ready\\film.mkv', 'report_only', { force_transcribe: true })
  })

  it('describes stored transcript state without claiming a fresh source verification', () => {
    row({ source: 'C:\\Ready\\film.mkv', status: 'transcribed', date_added: '', transcript: 'record.json', output: null, duration_seconds: null })
    expect(screen.getByText('Transcript recorded; source checked when used')).toBeInTheDocument()
  })

  it('offers explicit output replacement after incomplete provenance publication', () => {
    const submit = row({ source: 'C:\\Ready\\film.mkv', status: 'transcribed', date_added: '', transcript: 'record.json', output: 'finished.mkv', duration_seconds: null })
    expect(screen.queryByRole('button', { name: 'Play' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Recensor' }))
    expect(submit).toHaveBeenCalledWith('C:\\Ready\\film.mkv', 'censor', { overwrite_output: true })
  })

  it('shows the media length as a compact clock value', () => {
    row({ source: 'C:\\Ready\\film.mkv', status: 'ready', date_added: '', transcript: null, output: null, duration_seconds: 3723 })
    expect(screen.getByText('1:02:03')).toBeInTheDocument()
  })

  it('shows the same aggregate transcription speed and estimate in a table row', () => {
    const source = 'C:\\Ready\\film.mkv'
    row(
      { source, status: 'ready', date_added: '', transcript: null, output: null, duration_seconds: 399 },
      { id: 'job-1', source, mode: 'report_only', status: 'transcribing', progress_percent: 80, error: null },
      { event: 'progress', job_id: 'job-1', sequence: 1, stage: 'transcribing', percent: 80,
        eta_seconds: 20, fps: null, speed: 1.5, message: 'Transcribing audio' },
    )
    expect(screen.getByText('speed 1.50x · About 20s left')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '80')
  })

  it('does not present transcript saving as completed inference with zero time left', () => {
    const source = 'C:\\Ready\\film.mkv'
    row(
      { source, status: 'ready', date_added: '', transcript: null, output: null, duration_seconds: 399 },
      { id: 'job-1', source, mode: 'report_only', status: 'transcribing', progress_percent: 99, error: null },
      { event: 'progress', job_id: 'job-1', sequence: 1, stage: 'transcribing', percent: 99,
        eta_seconds: null, fps: null, speed: 1.5, message: 'Saving and verifying transcript' },
    )
    expect(screen.getByText('Saving and verifying transcript · speed 1.50x')).toBeInTheDocument()
    expect(screen.queryByText(/0s left/)).not.toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '99')
  })
})

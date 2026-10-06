import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { SystemCheck } from '../../types/domain'
import { SystemCheckPopover } from './SystemCheckPopover'

const completed: SystemCheck = { check_id: 'one', status: 'completed', stage: 'encoders', elapsed_ms: 10800,
  stage_elapsed_ms: 60, timings: { python_packages: 5520 }, capabilities: null, error: null }

describe('system verification popover', () => {
  it('keeps completed details collapsed, closes with focus recovery, and reopens without checking again', () => {
    const onRetry = vi.fn()
    render(<SystemCheckPopover className="runtime-pill" checking={false} state={completed} error={null} onRetry={onRetry}>Processing ready</SystemCheckPopover>)
    const trigger = screen.getByRole('button', { name: 'Processing ready' })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(trigger)
    expect(screen.getByText('System verification completed in 10.8s.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Close system verification' })).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'Close system verification' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    fireEvent.click(trigger)
    expect(screen.getByText(/Verifying processing packages: 5.52s/)).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    expect(onRetry).not.toHaveBeenCalled()
  })
  it('dismisses on outside clicks and retains actionable errors when reopened', () => {
    const onRetry = vi.fn()
    render(<SystemCheckPopover className="runtime-pill" checking={false} error="Contact interrupted" onRetry={onRetry}>Verification unavailable</SystemCheckPopover>)
    const trigger = screen.getByRole('button', { name: 'Verification unavailable' })
    fireEvent.click(trigger)
    expect(screen.getByRole('alert')).toHaveTextContent('Contact interrupted')
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(trigger)
    fireEvent.click(screen.getByRole('button', { name: 'Reconnect to system check' }))
    expect(onRetry).toHaveBeenCalledOnce()
    fireEvent.click(trigger)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})

import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SystemCheckStatus } from './SystemCheckStatus'

describe('system check status', () => {
  afterEach(() => vi.useRealTimers())
  it('shows elapsed time and resets it for a new check', async () => {
    vi.useFakeTimers()
    const onRetry = vi.fn()
    const view = render(<SystemCheckStatus checking error={null} onRetry={onRetry} />)
    expect(screen.getByRole('status')).toHaveTextContent('Verifying local processing packages')
    await act(() => vi.advanceTimersByTimeAsync(5000))
    expect(screen.getByText(/5s elapsed/)).toBeInTheDocument()
    view.rerender(<SystemCheckStatus checking={false} error="The check timed out" onRetry={onRetry} />)
    expect(screen.getByRole('alert')).toHaveTextContent('The check timed out')
    fireEvent.click(screen.getByRole('button', { name: 'Retry system check' }))
    expect(onRetry).toHaveBeenCalledOnce()
    view.rerender(<SystemCheckStatus checking error={null} onRetry={onRetry} />)
    expect(screen.getByText(/0s elapsed/)).toBeInTheDocument()
    view.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
  it('leaves the page clear when verification succeeds', () => {
    const view = render(<SystemCheckStatus checking={false} error={null} onRetry={vi.fn()} />)
    expect(view.container).toBeEmptyDOMElement()
  })
})

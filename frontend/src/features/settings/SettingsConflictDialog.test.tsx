import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { SettingsConflictDialog } from './SettingsConflictDialog'

it('requires explicit paired choices, traps focus, supports Escape and restores focus', async () => {
  const user = userEvent.setup()
  const trigger = document.createElement('button')
  document.body.append(trigger)
  trigger.focus()
  const cancel = vi.fn(), resolve = vi.fn()
  const conflicts = [
    { field: 'runtime.ffmpeg_path', expected: null, current: 'C:\\manual\\ffmpeg.exe', proposed: 'C:\\verified\\ffmpeg.exe' },
    { field: 'runtime.ffprobe_path', expected: null, current: null, proposed: 'C:\\verified\\ffprobe.exe' },
  ] as const
  const { unmount, rerender } = render(<SettingsConflictDialog revision="first" verified busy={false} onCancel={cancel} onResolve={resolve} conflicts={[...conflicts]} />)
  expect(screen.getByRole('dialog')).toHaveFocus()
  expect(screen.getByRole('button', { name: 'Apply choices' })).toBeDisabled()
  await user.tab()
  expect(screen.getAllByRole('radio')[0]).toHaveFocus()
  await user.click(screen.getAllByRole('radio')[1])
  expect(screen.getAllByRole('radio')[3]).toBeChecked()
  const apply = screen.getByRole('button', { name: 'Apply choices' })
  await user.click(apply)
  expect(resolve).toHaveBeenCalledWith({ 'runtime.ffmpeg_path': true, 'runtime.ffprobe_path': true })
  await user.tab()
  expect(screen.getAllByRole('radio')[0]).toHaveFocus()
  rerender(<SettingsConflictDialog revision="second" verified busy={false} onCancel={cancel} onResolve={resolve} conflicts={[...conflicts]} />)
  expect(screen.getByRole('dialog')).toHaveFocus()
  expect(apply).toBeDisabled()
  expect(screen.getAllByRole('radio').every((radio) => !(radio as HTMLInputElement).checked)).toBe(true)
  await user.keyboard('{Escape}')
  expect(cancel).toHaveBeenCalledOnce()
  unmount()
  expect(trigger).toHaveFocus()
  trigger.remove()
})

it('restores the captured save trigger after the browser blurred a disabled button', async () => {
  const trigger = document.createElement('button')
  document.body.append(trigger)
  trigger.focus()
  trigger.disabled = true
  trigger.blur()
  const { unmount } = render(<SettingsConflictDialog returnFocusTo={trigger} busy={false}
    onCancel={vi.fn()} onResolve={vi.fn()} conflicts={[
      { field: 'processing.device', expected: 'auto', current: 'cuda', proposed: 'cpu' },
    ]} />)
  unmount()
  trigger.disabled = false
  await waitFor(() => expect(trigger).toHaveFocus())
  trigger.remove()
})

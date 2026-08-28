import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SegmentedControl } from './SegmentedControl'

describe('SegmentedControl', () => {
  it('exposes its selection and reports the selected typed value', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <SegmentedControl
        label="Stereo method"
        value="drop_audio"
        options={[["drop_audio", 'Drop audio'], ['karaoke', 'Karaoke']]}
        onChange={onChange}
      />,
    )

    expect(screen.getByRole('button', { name: 'Drop audio' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await user.click(screen.getByRole('button', { name: 'Karaoke' }))
    expect(onChange).toHaveBeenCalledWith('karaoke')
  })
})

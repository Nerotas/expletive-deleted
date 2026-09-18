import { act, renderHook } from '@testing-library/react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { useColumnResize } from './use-column-resize'

function pointerStart() {
  const parent = document.createElement('div')
  const handle = document.createElement('span')
  parent.append(handle)
  vi.spyOn(parent, 'getBoundingClientRect').mockReturnValue({ width: 200 } as DOMRect)
  return {
    clientX: 100, currentTarget: handle, preventDefault: vi.fn(), stopPropagation: vi.fn(),
  } as unknown as ReactPointerEvent<HTMLSpanElement>
}

describe('column resizing lifecycle', () => {
  it('resizes and clamps columns while leaving other widths unchanged', () => {
    const { result } = renderHook(() => useColumnResize({ file: '200px', status: '150px' }))
    act(() => result.current.startColumnResize('file', pointerStart()))
    act(() => window.dispatchEvent(new MouseEvent('pointermove', { clientX: 150 })))
    expect(result.current.columnWidths).toEqual({ file: '250px', status: '150px' })
    act(() => window.dispatchEvent(new MouseEvent('pointermove', { clientX: -200 })))
    expect(result.current.columnWidths.file).toBe('110px')
    act(() => window.dispatchEvent(new Event('pointerup')))
  })

  it.each(['pointerup', 'pointercancel', 'blur'])('stops resizing after %s', (eventName) => {
    const { result } = renderHook(() => useColumnResize({ file: '200px' }))
    act(() => result.current.startColumnResize('file', pointerStart()))
    act(() => window.dispatchEvent(new Event(eventName)))
    act(() => window.dispatchEvent(new MouseEvent('pointermove', { clientX: 500 })))
    expect(result.current.columnWidths.file).toBe('200px')
  })

  it('removes every window listener when navigation unmounts the table mid-drag', () => {
    const add = vi.spyOn(window, 'addEventListener')
    const remove = vi.spyOn(window, 'removeEventListener')
    const { result, unmount } = renderHook(() => useColumnResize({ file: '200px' }))
    act(() => result.current.startColumnResize('file', pointerStart()))
    const listeners = add.mock.calls.filter(([event]) => ['pointermove', 'pointerup', 'pointercancel', 'blur'].includes(event))
    expect(listeners).toHaveLength(4)
    unmount()
    for (const [event, listener] of listeners) expect(remove).toHaveBeenCalledWith(event, listener)
  })

  it('ends the previous drag before starting another column', () => {
    const { result } = renderHook(() => useColumnResize({ file: '200px', status: '150px' }))
    act(() => result.current.startColumnResize('file', pointerStart()))
    act(() => result.current.startColumnResize('status', pointerStart()))
    act(() => window.dispatchEvent(new MouseEvent('pointermove', { clientX: 150 })))
    expect(result.current.columnWidths).toEqual({ file: '200px', status: '250px' })
  })

  it('applies the same minimum width to keyboard resizing', () => {
    const { result } = renderHook(() => useColumnResize({ file: '120px' }))
    act(() => result.current.resizeColumnBy('file', 120, -12))
    expect(result.current.columnWidths.file).toBe('110px')
  })
})

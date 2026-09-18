import { useEffect, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'

const MIN_COLUMN_WIDTH = 110

export function useColumnResize<Column extends string>(initialWidths: Record<Column, string>) {
  const [columnWidths, setColumnWidths] = useState(initialWidths)
  const stopResizeRef = useRef<(() => void) | null>(null)

  // Route changes can unmount the table before pointerup reaches the window.
  useEffect(() => () => stopResizeRef.current?.(), [])

  const resizeColumnBy = (column: Column, baseWidth: number, delta: number) => {
    setColumnWidths((current) => ({
      ...current,
      [column]: `${Math.max(MIN_COLUMN_WIDTH, baseWidth + delta)}px`,
    }))
  }

  const startColumnResize = (column: Column, event: ReactPointerEvent<HTMLSpanElement>) => {
    event.preventDefault()
    event.stopPropagation()
    stopResizeRef.current?.()
    const startX = event.clientX
    const startWidth = event.currentTarget.parentElement?.getBoundingClientRect().width ?? MIN_COLUMN_WIDTH
    const resize = (moveEvent: PointerEvent) => resizeColumnBy(column, startWidth, moveEvent.clientX - startX)
    const stopResize = () => {
      window.removeEventListener('pointermove', resize)
      window.removeEventListener('pointerup', stopResize)
      window.removeEventListener('pointercancel', stopResize)
      window.removeEventListener('blur', stopResize)
      stopResizeRef.current = null
    }
    stopResizeRef.current = stopResize
    window.addEventListener('pointermove', resize)
    window.addEventListener('pointerup', stopResize, { once: true })
    window.addEventListener('pointercancel', stopResize, { once: true })
    window.addEventListener('blur', stopResize, { once: true })
  }

  return { columnWidths, startColumnResize, resizeColumnBy }
}

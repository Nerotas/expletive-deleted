type NumberInputProps = {
  value: number
  onChange: (value: number) => void
  unit?: string
  min?: number
  max?: number
  label?: string
}

export function NumberInput({
  value,
  onChange,
  unit = 'ms',
  min = 0,
  max = 10_000,
  label,
}: NumberInputProps) {
  return (
    <div className="number-input">
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        aria-label={label}
        onChange={(event) => onChange(Number(event.target.value))}
      />
      <span>{unit}</span>
    </div>
  )
}

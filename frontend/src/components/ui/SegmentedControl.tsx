type SegmentedControlProps<T extends string> = {
  value: T
  options: ReadonlyArray<readonly [T, string]>
  onChange: (value: T) => void
  label?: string
}

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  label,
}: SegmentedControlProps<T>) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map(([option, optionLabel]) => (
        <button
          type="button"
          className={value === option ? 'selected' : ''}
          aria-pressed={value === option}
          onClick={() => onChange(option)}
          key={option}
        >
          {optionLabel}
        </button>
      ))}
    </div>
  )
}


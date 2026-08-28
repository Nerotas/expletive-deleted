import type { ReactNode } from 'react'

export function SettingsSection({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <section className="settings-section">
      <header>
        <h2>{title}</h2>
        <p>{description}</p>
      </header>
      <div className="settings-content">{children}</div>
    </section>
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field">
      <span>{label}</span>
      {children}
    </div>
  )
}

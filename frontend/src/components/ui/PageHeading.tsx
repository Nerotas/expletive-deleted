import type { ReactNode } from 'react'

type PageHeadingProps = {
  title: string
  subtitle: string
  children?: ReactNode
}

export function PageHeading({ title, subtitle, children }: PageHeadingProps) {
  return (
    <div className="page-heading">
      <div>
        <span className="eyebrow">Workspace</span>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <div className="heading-actions">{children}</div>
    </div>
  )
}


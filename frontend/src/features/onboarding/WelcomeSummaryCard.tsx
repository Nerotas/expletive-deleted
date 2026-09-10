import type { ReactNode } from 'react'

type WelcomeSummaryCardProps = {
  icon: ReactNode
  title: string
  detail: string
}

export function WelcomeSummaryCard({ icon, title, detail }: WelcomeSummaryCardProps) {
  return <article>
    {icon}
    <strong>{title}</strong>
    <span>{detail}</span>
  </article>
}
type CensoringMethodCardProps = {
  title: string
  description: string
  note: string
  selected: boolean
}

export function CensoringMethodCard({ title, description, note, selected }: CensoringMethodCardProps) {
  return <article className={selected ? 'selected' : undefined}>
    <h3>{title}</h3>
    <p>{description}</p>
    <strong>{note}</strong>
  </article>
}
type WorkflowInstructionCardProps = {
  number: string
  title: string
  description: string
}

export function WorkflowInstructionCard({ number, title, description }: WorkflowInstructionCardProps) {
  return <article>
    <span>{number}</span>
    <h3>{title}</h3>
    <p>{description}</p>
  </article>
}
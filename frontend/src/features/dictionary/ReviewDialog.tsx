import { useState } from 'react'
import type { DictionaryTarget, ReviewResult } from '../../types/domain'
import { fileName, formatEta } from '../../utils/format'

type ReviewDialogProps = {
  review: ReviewResult
  busy: boolean
  onClose: () => void
  onClassify: (word: string, target: DictionaryTarget) => void
}

export function ReviewDialog({ review, busy, onClose, onClassify }: ReviewDialogProps) {
  const [category, setCategory] = useState<'discovered' | 'censored'>('discovered')
  const words = category === 'discovered' ? review.candidates : review.censored

  return (
    <div className="modal-backdrop">
      <section className="modal review-dialog" role="dialog" aria-modal="true" aria-labelledby="review-title">
        <span className="eyebrow">Potential profanity</span>
        <h2 id="review-title">Review discovered words</h2>
        <p>{fileName(review.source)} · Review words found in this transcript and update your policy when needed.</p>
        <div className="review-tabs" role="group" aria-label="Review word category">
          <button
            type="button"
            aria-pressed={category === 'discovered'}
            onClick={() => setCategory('discovered')}
          >
            {`Discovered words (${review.candidates.length})`}
          </button>
          <button
            type="button"
            aria-pressed={category === 'censored'}
            onClick={() => setCategory('censored')}
          >
            {`Censored words (${review.censored.length})`}
          </button>
        </div>
        {words.length ? (
          <div className="review-list">
            {words.map((candidate, index) => (
              <div key={`${candidate.word}-${candidate.start}-${index}`}>
                <strong>{candidate.word}</strong>
                <span>{candidate.start != null ? `${formatEta(candidate.start)} in` : 'Timestamp unavailable'}</span>
                {category === 'discovered' && <>
                  <button disabled={busy} onClick={() => onClassify(candidate.word, 'censor')}>Censor</button>
                  <button disabled={busy} onClick={() => onClassify(candidate.word, 'exclude')}>Ignore</button>
                </>}
              </div>
            ))}
          </div>
        ) : <div className="empty-review">{category === 'discovered' ? 'No unclassified potential profanity was found.' : 'No censored words were found in this transcript.'}</div>}
        <div className="modal-actions">
          <button className="button secondary" onClick={onClose}>Close</button>
        </div>
      </section>
    </div>
  )
}


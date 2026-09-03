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
  const [revealed, setRevealed] = useState(false)

  return (
    <div className="modal-backdrop">
      <section className="modal review-dialog" role="dialog" aria-modal="true" aria-labelledby="review-title">
        <span className="eyebrow">Potential profanity</span>
        <h2 id="review-title">Review discovered words</h2>
        <p>{fileName(review.source)} · These vendor-list matches are not in your current policy.</p>
        <div className="review-toolbar">
          <button
            type="button"
            className="button secondary"
            aria-pressed={revealed}
            onClick={() => setRevealed((current) => !current)}
          >
            {revealed ? 'Hide words' : 'Reveal words'}
          </button>
          <small>Words stay masked until you choose to reveal them.</small>
        </div>
        {review.candidates.length ? (
          <div className="review-list">
            {review.candidates.map((candidate, index) => (
              <div key={`${candidate.word}-${candidate.start}-${index}`}>
                <strong>{revealed ? candidate.word : candidate.word.replace(/\S/g, '•')}</strong>
                <span>{candidate.start != null ? `${formatEta(candidate.start)} in` : 'Timestamp unavailable'}</span>
                <button disabled={busy} onClick={() => onClassify(candidate.word, 'censor')}>Censor</button>
                <button disabled={busy} onClick={() => onClassify(candidate.word, 'exclude')}>Ignore</button>
              </div>
            ))}
          </div>
        ) : <div className="empty-review">No unclassified potential profanity was found.</div>}
        <div className="modal-actions">
          <button className="button secondary" onClick={onClose}>Close</button>
        </div>
      </section>
    </div>
  )
}


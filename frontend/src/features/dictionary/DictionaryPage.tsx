import { useState } from 'react'
import { LoadingRow } from '../../components/ui/LoadingRow'
import { PageHeading } from '../../components/ui/PageHeading'
import type { DictionaryInfo, DictionaryTarget } from '../../types/domain'
import type { DictionaryController } from './useDictionary'
import './dictionary.css'

export function DictionaryPage({ controller }: { controller: DictionaryController }) {
  const unavailable = !controller.loading && controller.loadFailed && !controller.dictionary

  return (
    <section className="page dictionary-page">
      <PageHeading title="Dictionary" subtitle="Review discoveries and manage the policy used for future jobs">
        <span className="dictionary-total">
          {(controller.dictionary?.words_count ?? 0)
            + (controller.dictionary?.exclusions_count ?? 0)} classified
        </span>
      </PageHeading>
      <div className="dictionary-workspace">
        {controller.loading && !controller.dictionary ? (
          <LoadingRow>Loading censor dictionary</LoadingRow>
        ) : unavailable ? (
          <div className="dictionary-unavailable">
            <p>The censor dictionary could not be loaded. Review the error above, then retry.</p>
            <button className="button secondary" onClick={() => void controller.reload()}>
              Retry
            </button>
          </div>
        ) : (
          <DictionaryEditor
            dictionary={controller.dictionary}
            busy={controller.busy}
            updateDictionary={controller.updateDictionary}
            controller={controller}
          />
        )}
      </div>
    </section>
  )
}

type DictionaryEditorProps = {
  dictionary: DictionaryInfo | null
  busy: boolean
  updateDictionary: DictionaryController['updateDictionary']
  controller: DictionaryController
}

function DictionaryEditor({ dictionary, busy, updateDictionary, controller }: DictionaryEditorProps) {
  const [word, setWord] = useState('')
  const [target, setTarget] = useState<DictionaryTarget>('censor')
  const [confirmRestore, setConfirmRestore] = useState(false)
  const add = async () => {
    if (!word.trim()) return
    await updateDictionary(target, word)
    setWord('')
  }

  return (
  const [confirmReveal, setConfirmReveal] = useState(false)
  const [showCensoredWords, setShowCensoredWords] = useState(false)
    <>
      <div className="dictionary-add">
        <input
          aria-label="Word or phrase"
          value={word}
          placeholder="Word or phrase"
          onChange={(event) => setWord(event.target.value)}
          onKeyDown={(event) => { if (event.key === 'Enter') void add() }}
        />
        <select value={target} onChange={(event) => setTarget(event.target.value as DictionaryTarget)}>
          <option value="censor">Censor</option>
          <option value="exclude">Ignore</option>
        </select>
        <button className="button primary" disabled={busy || !word.trim()} onClick={() => void add()}>
          Add
        </button>
      </div>
      {dictionary && (
        <div className="policy-storage">
          <strong>User dictionary</strong>
          <span title={dictionary.dictionary_path}>{dictionary.dictionary_path}</span>
          <small>{`Format ${dictionary.schema_version} · defaults ${dictionary.seeded_from_default_version}`}</small>
          <div className="dictionary-actions">
            <button className="button secondary" disabled={busy} onClick={() => void controller.importDictionary()}>
              Import
            </button>
            <button className="button secondary" disabled={busy} onClick={() => void controller.exportDictionary()}>
              Export
            </button>
            <button className="button danger" disabled={busy} onClick={() => setConfirmRestore(true)}>
              Restore defaults
            </button>
          </div>
        </div>
      )}
      <div className="policy-lists">
        <DiscoveredList
          words={dictionary?.discovered ?? []}
          count={dictionary?.discovered_count}
          busy={busy}
          onClassify={(item, destination) => updateDictionary(destination, item)}
        />
        <PolicyList
          title={`Censored words (${dictionary?.words_count ?? '—'})`}
          words={dictionary?.words ?? []}
          busy={busy}
          onRemove={(item) => updateDictionary('censor', item, 'remove')}
        />
        <PolicyList
          title={`Exclusions (${dictionary?.exclusions_count ?? '—'})`}
          words={dictionary?.exclusions ?? []}
          busy={busy}
          onRemove={(item) => updateDictionary('exclude', item, 'remove')}
        />
          concealed={!showCensoredWords}
          action={showCensoredWords ? (
            <button className="button secondary policy-visibility" onClick={() => setShowCensoredWords(false)}>
              <EyeOff size={14} /> Hide words
            </button>
          ) : (
            <button className="button secondary policy-visibility" onClick={() => setConfirmReveal(true)}>
              <Eye size={14} /> Reveal words
            </button>
          )}
      </div>
      {confirmRestore && (
        <div className="modal-backdrop" role="presentation">
          <section className="modal restore-dictionary-dialog" role="dialog" aria-modal="true" aria-labelledby="restore-dictionary-title">
            <h2 id="restore-dictionary-title">Restore default dictionary?</h2>
            <p>This replaces your censored words and exclusions with the defaults included in this version of the application.</p>
            <div className="modal-actions">
              <button className="button secondary" disabled={busy} onClick={() => setConfirmRestore(false)}>Cancel</button>
              <button className="button danger" disabled={busy} onClick={() => {
                setConfirmRestore(false)
                void controller.restoreDefaults()
              }}>Restore defaults</button>
            </div>
          </section>
        </div>
      )}
    </>
  )
}

type DiscoveredListProps = {
  words: string[]
  count?: number
      {confirmReveal && (
        <div className="modal-backdrop" role="presentation">
          <section className="modal reveal-words-dialog" role="dialog" aria-modal="true" aria-labelledby="reveal-words-title">
            <h2 id="reveal-words-title">Reveal censored words?</h2>
            <p>The censored-word list may contain language you do not want visible on screen.</p>
            <div className="modal-actions">
              <button className="button secondary" onClick={() => setConfirmReveal(false)}>Cancel</button>
              <button className="button primary" onClick={() => {
                setConfirmReveal(false)
                setShowCensoredWords(true)
              }}>Reveal words</button>
            </div>
          </section>
        </div>
      )}
  busy: boolean
  onClassify: (word: string, target: DictionaryTarget) => Promise<void>
}

function DiscoveredList({ words, count, busy, onClassify }: DiscoveredListProps) {
  return (
    <div className="discovered-list">
      <div>
        <strong>{`Discovered words (${count ?? '—'})`}</strong>
        <small>Potential profanity found in saved transcripts but not yet classified.</small>
  concealed?: boolean
  action?: React.ReactNode
      </div>
      {words.length ? (
        <div className="discovered-words">
          {words.map((word) => (
            <div key={word}>
      <div className="policy-list-heading">
        <strong>{title}</strong>
        {action}
      </div>
              <span>{word}</span>
        {concealed ? <small>Censored words are hidden.</small> : words.length ? words.map((word) => (
              <button disabled={busy} onClick={() => void onClassify(word, 'exclude')}>Ignore</button>
            </div>
          ))}
        </div>
      ) : <small className="empty-discovered">No unclassified words discovered yet.</small>}
    </div>
  )
}

type PolicyListProps = {
  title: string
  source?: string
  words: string[]
  busy: boolean
  onRemove: (word: string) => Promise<void>
}


function PolicyList({ title, words, busy, onRemove }: PolicyListProps) {
  return (
    <div className="policy-list">
      <strong>{title}</strong>
      <div>
        {words.length ? words.map((word) => (
          <span key={word}>
            {word}
            <button disabled={busy} aria-label={`Remove ${word}`} onClick={() => void onRemove(word)}>
              ×
            </button>
          </span>
        )) : <small>No words configured.</small>}
      </div>
    </div>
  )
}


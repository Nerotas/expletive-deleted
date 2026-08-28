import { useState } from 'react'
import { PageHeading } from '../../components/ui/PageHeading'
import type { DictionaryInfo, DictionaryTarget } from '../../types/domain'
import type { DictionaryController } from './useDictionary'
import './dictionary.css'

export function DictionaryPage({ controller }: { controller: DictionaryController }) {
  return (
    <section className="page dictionary-page">
      <PageHeading title="Dictionary" subtitle="Review discoveries and manage the policy used for future jobs">
        <span className="dictionary-total">
          {(controller.dictionary?.words_count ?? 0)
            + (controller.dictionary?.exclusions_count ?? 0)} classified
        </span>
      </PageHeading>
      <div className="dictionary-workspace">
        <DictionaryEditor
          dictionary={controller.dictionary}
          busy={controller.busy}
          updateDictionary={controller.updateDictionary}
        />
      </div>
    </section>
  )
}

type DictionaryEditorProps = {
  dictionary: DictionaryInfo | null
  busy: boolean
  updateDictionary: DictionaryController['updateDictionary']
}

function DictionaryEditor({ dictionary, busy, updateDictionary }: DictionaryEditorProps) {
  const [word, setWord] = useState('')
  const [target, setTarget] = useState<DictionaryTarget>('censor')
  const add = async () => {
    if (!word.trim()) return
    await updateDictionary(target, word)
    setWord('')
  }

  return (
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
      </div>
    </>
  )
}

type DiscoveredListProps = {
  words: string[]
  count?: number
  busy: boolean
  onClassify: (word: string, target: DictionaryTarget) => Promise<void>
}

function DiscoveredList({ words, count, busy, onClassify }: DiscoveredListProps) {
  return (
    <div className="discovered-list">
      <div>
        <strong>{`Discovered words (${count ?? '—'})`}</strong>
        <small>Potential profanity found in saved transcripts but not yet classified.</small>
      </div>
      {words.length ? (
        <div className="discovered-words">
          {words.map((word) => (
            <div key={word}>
              <span>{word}</span>
              <button disabled={busy} onClick={() => void onClassify(word, 'censor')}>Censor</button>
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


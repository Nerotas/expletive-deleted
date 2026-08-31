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
      {dictionary && (
        <div className="policy-storage">
          <strong>User policy</strong>
          <span title={dictionary.overrides_path}>{dictionary.overrides_path}</span>
          <small>
            {dictionary.overrides_count
              ? `${dictionary.overrides_count} saved override${dictionary.overrides_count === 1 ? '' : 's'}`
              : 'No user overrides yet'}
          </small>
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
          source={dictionary?.words_path}
          words={dictionary?.words ?? []}
          busy={busy}
          onRemove={(item) => updateDictionary('censor', item, 'remove')}
        />
        <PolicyList
          title={`Exclusions (${dictionary?.exclusions_count ?? '—'})`}
          source={dictionary?.exclusions_path}
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
  source?: string
  words: string[]
  busy: boolean
  onRemove: (word: string) => Promise<void>
}

function policySourceLabel(source: string): string {
  const normalized = source.replaceAll('\\', '/')
  const resources = normalized.lastIndexOf('/resources/')
  return resources >= 0 ? normalized.slice(resources + 1) : source
}

function PolicyList({ title, source, words, busy, onRemove }: PolicyListProps) {
  return (
    <div className="policy-list">
      <strong>{title}</strong>
      {source && (
        <small className="policy-source" title={source}>
          Built-in defaults: {policySourceLabel(source)}
        </small>
      )}
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


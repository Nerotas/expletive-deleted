import { useState } from 'react'
import { Search } from 'lucide-react'
import { PageHeading } from '../../components/ui/PageHeading'
import type { DictionaryTarget } from '../../types/domain'
import type { DictionaryController } from './useDictionary'
import './dictionary.css'

import { DictionaryTable } from './DictionaryTable'

export function DictionaryPage({ controller }: { controller: DictionaryController }) {
  return (
    <section className="page dictionary-page">
      <PageHeading title="Dictionary" subtitle="Review discoveries and manage the policy used for future jobs">
        <span className="dictionary-total">
          {`${controller.entries?.total ?? 0} ${controller.target === 'exclude' ? 'exclusions' : 'censored words'}`}
        </span>
      </PageHeading>
      <div className="dictionary-workspace">
        <DictionaryEditor controller={controller} />
      </div>
    </section>
  )
}

function DictionaryEditor({ controller }: { controller: DictionaryController }) {
  const [word, setWord] = useState('')
  const [destination, setDestination] = useState<DictionaryTarget>('censor')
  const [confirmRestore, setConfirmRestore] = useState(false)
  const [confirmReveal, setConfirmReveal] = useState(false)
  const add = async () => {
    if (!word.trim()) return
    await controller.updateDictionary(destination, word)
    setWord('')
  }
  const selectCensored = () => {
    if (controller.censoredWordsRevealed) controller.revealCensoredWords()
    else setConfirmReveal(true)
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
        <select value={destination} onChange={(event) => setDestination(event.target.value as DictionaryTarget)}>
          <option value="censor">Censor</option>
          <option value="exclude">Ignore</option>
        </select>
        <button className="button primary" disabled={controller.busy || !word.trim()} onClick={() => void add()}>
          Add
        </button>
      </div>
      {controller.info && (
        <div className="policy-storage">
          <strong>User dictionary</strong>
          <span title={controller.info.dictionary_path}>{controller.info.dictionary_path}</span>
          <small>{`Format ${controller.info.schema_version} · defaults ${controller.info.seeded_from_default_version}`}</small>
          <div className="dictionary-actions">
            <button className="button secondary" disabled={controller.busy} onClick={() => void controller.importDictionary()}>Import</button>
            <button className="button secondary" disabled={controller.busy} onClick={() => void controller.exportDictionary()}>Export</button>
            <button className="button danger" disabled={controller.busy} onClick={() => setConfirmRestore(true)}>Restore defaults</button>
          </div>
        </div>
      )}
      <DiscoveredList
        words={controller.discovered}
        busy={controller.busy}
        onClassify={(item, target) => controller.updateDictionary(target, item)}
      />
      <div className="dictionary-table-tools">
        <div className="dictionary-tabs" role="group" aria-label="Dictionary category">
          <button
            type="button"
            aria-pressed={controller.target === 'exclude'}
            onClick={controller.showExclusions}
          >
            {`Exclusions${controller.target === 'exclude' ? ` (${controller.entries?.total ?? 0})` : ''}`}
          </button>
          <button
            type="button"
            aria-pressed={controller.target === 'censor'}
            onClick={selectCensored}
          >
            {`Censored words${controller.target === 'censor' ? ` (${controller.entries?.total ?? 0})` : ''}`}
          </button>
        </div>
        <label className="dictionary-search">
          <Search size={15} aria-hidden="true" />
          <input
            type="search"
            aria-label="Search dictionary"
            value={controller.search}
            placeholder="Search"
            onChange={(event) => controller.setSearch(event.target.value)}
          />
        </label>
      </div>
      <DictionaryTable controller={controller} />
      {confirmRestore && (
        <div className="modal-backdrop" role="presentation">
          <section className="modal restore-dictionary-dialog" role="dialog" aria-modal="true" aria-labelledby="restore-dictionary-title">
            <h2 id="restore-dictionary-title">Restore default dictionary?</h2>
            <p>This replaces your censored words and exclusions with the defaults included in this version of the application.</p>
            <div className="modal-actions">
              <button className="button secondary" disabled={controller.busy} onClick={() => setConfirmRestore(false)}>Cancel</button>
              <button className="button danger" disabled={controller.busy} onClick={() => {
                setConfirmRestore(false)
                void controller.restoreDefaults()
              }}>Restore defaults</button>
            </div>
          </section>
        </div>
      )}
      {confirmReveal && (
        <div className="modal-backdrop" role="presentation">
          <section className="modal reveal-words-dialog" role="dialog" aria-modal="true" aria-labelledby="reveal-words-title">
            <h2 id="reveal-words-title">Reveal censored words?</h2>
            <p>The censored-word list may contain language you do not want visible on screen.</p>
            <div className="modal-actions">
              <button className="button secondary" onClick={() => setConfirmReveal(false)}>Cancel</button>
              <button className="button primary" onClick={() => {
                setConfirmReveal(false)
                controller.revealCensoredWords()
              }}>Reveal words</button>
            </div>
          </section>
        </div>
      )}
    </>
  )
}

type DiscoveredListProps = {
  words: string[]
  busy: boolean
  onClassify: (word: string, target: DictionaryTarget) => Promise<void>
}

function DiscoveredList({ words, busy, onClassify }: DiscoveredListProps) {
  return (
    <div className="discovered-list">
      <div>
        <strong>{`Discovered words (${words.length})`}</strong>
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

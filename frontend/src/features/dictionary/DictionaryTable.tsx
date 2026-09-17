import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react'
import { LoadingRow } from '../../components/ui/LoadingRow'
import type { DictionarySort } from '../../types/domain'
import type { DictionaryController } from './useDictionary'

const SOURCE_LABELS = { default: 'Default', user: 'User', imported: 'Imported' } as const

export function DictionaryTable({ controller }: { controller: DictionaryController }) {
  const entries = controller.entries
  if (controller.tableLoading && !entries) {
    return <div className="dictionary-table-loading"><LoadingRow>Loading dictionary entries</LoadingRow></div>
  }
  if (controller.tableFailed && !entries) {
    return (
      <div className="dictionary-table-loading dictionary-unavailable">
        <p>The selected dictionary entries could not be loaded.</p>
        <button className="button secondary" onClick={() => void controller.reload()}>Retry</button>
      </div>
    )
  }

  return (
    <div className="dictionary-table-region">
      <table className="dictionary-table">
        <thead>
          <tr>
            <SortableHeading label="Word or phrase" field="value" controller={controller} />
            <SortableHeading label="Added" field="added_at" controller={controller} />
            <SortableHeading label="Source" field="source" controller={controller} />
            <th scope="col" className="dictionary-action-column">Actions</th>
          </tr>
        </thead>
        <tbody>
          {entries?.items.length ? entries.items.map((entry) => (
            <tr key={entry.value}>
              <td className="dictionary-word">{entry.value}</td>
              <td>{entry.source === 'default' ? 'Default' : new Date(entry.added_at).toLocaleString()}</td>
              <td><span className={`dictionary-source source-${entry.source}`}>{SOURCE_LABELS[entry.source]}</span></td>
              <td className="dictionary-action-column">
                <button
                  className="icon-button dictionary-remove"
                  disabled={controller.busy}
                  aria-label={`Remove ${entry.value}`}
                  title={`Remove ${entry.value}`}
                  onClick={() => void controller.updateDictionary(controller.target, entry.value, 'remove')}
                >
                  <Trash2 size={16} aria-hidden="true" />
                </button>
              </td>
            </tr>
          )) : (
            <tr><td colSpan={4} className="dictionary-empty">No matching entries.</td></tr>
          )}
        </tbody>
      </table>
      <div className="dictionary-pagination">
        <span>{entries ? `${entries.total} entries · Page ${entries.page} of ${Math.max(entries.total_pages, 1)}` : '0 entries'}</span>
        <div>
          <button className="button secondary" disabled={!entries || entries.page <= 1 || controller.busy} onClick={() => controller.setPage(controller.page - 1)}>Previous</button>
          <button className="button secondary" disabled={!entries || entries.page >= entries.total_pages || controller.busy} onClick={() => controller.setPage(controller.page + 1)}>Next</button>
        </div>
      </div>
    </div>
  )
}

function SortableHeading({
  label,
  field,
  controller,
}: {
  label: string
  field: DictionarySort
  controller: DictionaryController
}) {
  const active = controller.sort === field
  return (
    <th scope="col">
      <button type="button" onClick={() => controller.setSort(field)}>
        {label}
        {active && (controller.direction === 'asc'
          ? <ArrowUp size={13} aria-label="ascending" />
          : <ArrowDown size={13} aria-label="descending" />)}
      </button>
    </th>
  )
}

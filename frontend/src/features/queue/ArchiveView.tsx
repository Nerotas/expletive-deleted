import { ArchiveIcon, RotateCcw, Trash2 } from 'lucide-react'
import type { ArchiveItem } from '../../types/domain'
import { fileName, formatBytes } from '../../utils/format'

export function ArchiveView({ items, busy, archivePath, queueIdle, onRestore, onPurge }: { items: ArchiveItem[]; busy: boolean; archivePath?: string; queueIdle: boolean; onRestore: (source: string) => Promise<unknown>; onPurge: (item: ArchiveItem) => void }) {
  return <>
    <div className="archive-note">Archived originals are kept for inspection. Return one to Queue when you want it back in Ready; it will not overwrite an existing file.</div>
    <div className="table-frame archive-table-frame"><table className="archive-table">
      <thead><tr><th>Original</th><th>Archived</th><th>Size</th><th>Actions</th></tr></thead>
      <tbody>
        {items.map((item) => <tr key={item.source}>
          <td><div className="file-cell"><span className="file-icon">{fileName(item.source).split('.').pop()?.toUpperCase()}</span><div><strong>{fileName(item.source)}</strong><small>{item.relative_path}</small></div></div></td>
          <td>{new Date(item.archived_at).toLocaleDateString()}</td>
          <td>{formatBytes(item.size_bytes)}</td>
          <td className="details-cell"><button disabled={busy || !queueIdle} title={!queueIdle ? 'Wait until the processing queue is idle before returning a file' : 'Move this original back to Ready'} onClick={() => void onRestore(item.source)}><RotateCcw size={13} />Return to Queue</button><button disabled={busy} onClick={() => onPurge(item)}><Trash2 size={13} />Delete permanently</button></td>
        </tr>)}
        {!items.length && <tr><td colSpan={4}><div className="empty-state"><ArchiveIcon size={28} /><strong>No archived originals</strong><span>After checking a finished file, choose Archive source to keep its original here.</span></div></td></tr>}
      </tbody>
    </table></div>
    <div className="path-bar"><ArchiveIcon size={16} /><span>{archivePath}</span></div>
  </>
}

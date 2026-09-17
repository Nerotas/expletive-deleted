import { useState } from 'react'
import { LoaderCircle } from 'lucide-react'
import type { YoutubeSubmitResult } from './useQueue'

export type YoutubeAuthenticationRequest = { url: string; retryId?: string; cookiesUnavailable?: boolean; diagnostic?: string }

export function YoutubeDialog({ available, busy, onCancel, onReviewSetup, onConfirm }: { available: boolean; busy: boolean; onCancel: () => void; onReviewSetup: () => void; onConfirm: (url: string, browser?: string) => Promise<void> }) {
  const [url, setUrl] = useState('')
  const [useBrowserCookies, setUseBrowserCookies] = useState(false)
  const [browser, setBrowser] = useState('firefox')
  const valid = /^https?:\/\/(www\.|m\.)?(youtube\.com\/watch\?[^\s]*\bv=|youtu\.be\/)[^\s]+/i.test(url)
  return <div className="modal-backdrop" role="presentation"><section className="modal youtube-dialog" role="dialog" aria-modal="true" aria-labelledby="youtube-dialog-title">
    <p className="eyebrow">YouTube import</p><h2 id="youtube-dialog-title">Download from YouTube</h2>
    {available ? <><div className="youtube-form-row"><label htmlFor="youtube-url">YouTube URL</label><input id="youtube-url" type="url" value={url} placeholder="https://www.youtube.com/watch?v=..." onChange={(event) => setUrl(event.target.value)} autoFocus /></div>
      <div className="youtube-form-row"><label className="youtube-checkbox"><input type="checkbox" checked={useBrowserCookies} disabled={busy} onChange={(event) => setUseBrowserCookies(event.target.checked)} /> Use my signed-in browser session</label></div>
      {useBrowserCookies && <div className="youtube-form-row"><label htmlFor="youtube-cookie-browser">Browser session</label><select id="youtube-cookie-browser" value={browser} disabled={busy} onChange={(event) => setBrowser(event.target.value)}><option value="firefox">Firefox</option><option value="chrome">Chrome</option><option value="edge">Microsoft Edge</option><option value="brave">Brave</option></select><small>Chrome, Edge, and Brave currently block yt-dlp on Windows; Firefox is recommended until that is fixed.</small></div>}
      <p>Only download media you are authorized to download and process.</p><div className="modal-actions"><button className="button secondary" disabled={busy} onClick={onCancel}>Cancel</button><button className="button primary" disabled={busy || !valid} onClick={() => void onConfirm(url, useBrowserCookies ? browser : undefined)}>{busy ? <><LoaderCircle className="spin" size={16} />Adding to Queue…</> : 'Add to Queue'}</button></div></>
      : <><p>yt-dlp is required for YouTube downloads. Review the local setup plan, then return here to add an individual video.</p><div className="modal-actions"><button className="button secondary" onClick={onCancel}>Cancel</button><button className="button primary" onClick={onReviewSetup}>Review YouTube setup</button></div></>}
  </section></div>
}

export function YoutubeAuthenticationDialog({ busy, cookiesUnavailable, diagnostic, onCancel, onOpenYoutube, onRetry }: { busy: boolean; cookiesUnavailable?: boolean; diagnostic?: string; onCancel: () => void; onOpenYoutube: () => void; onRetry: (browser: string) => Promise<YoutubeSubmitResult> }) {
  const [browser, setBrowser] = useState(cookiesUnavailable ? 'firefox' : 'chrome')
  return <div className="modal-backdrop" role="presentation"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="youtube-auth-dialog-title">
    <p className="eyebrow">YouTube authentication required</p>
    <h2 id="youtube-auth-dialog-title">YouTube needs your browser session</h2>
    <p>{cookiesUnavailable ? 'Windows blocks yt-dlp from reading Chrome, Edge, and Brave cookie databases on many current versions of those browsers, even after fully closing them. This is a known limitation outside of this application\u2019s control.' : 'YouTube would not allow this video to be downloaded without a signed-in or verified browser session.'}</p>
    <p>{cookiesUnavailable ? 'Firefox does not have this restriction. If you are signed into YouTube in Firefox, select it below and retry. Expletive Deleted does not receive your YouTube password; cookies stay local on your computer.' : 'Expletive Deleted can retry through yt-dlp using a browser where you are already signed into YouTube. It does not receive your YouTube password; cookies stay local on your computer.'}</p>
    {diagnostic && <details className="job-diagnostic">
      <summary>Technical details</summary>
      <pre>{diagnostic}</pre>
    </details>}
    <label htmlFor="youtube-cookie-browser">Browser session</label>
    <select id="youtube-cookie-browser" value={browser} disabled={busy} onChange={(event) => setBrowser(event.target.value)}>
      <option value="firefox">Firefox</option><option value="chrome">Chrome</option><option value="edge">Microsoft Edge</option><option value="brave">Brave</option>
    </select>
    <p>You may open YouTube to sign in or complete verification, then return here. Opening YouTube does not retry this download.</p>
    <div className="modal-actions">
      <button className="button secondary" disabled={busy} onClick={onCancel}>Cancel</button>
      <button className="button secondary" disabled={busy} onClick={onOpenYoutube}>Open YouTube</button>
      <button className="button primary" disabled={busy} onClick={() => void onRetry(browser)}>Retry with {browser === 'edge' ? 'Microsoft Edge' : browser[0].toUpperCase() + browser.slice(1)}</button>
    </div>
  </section></div>
}

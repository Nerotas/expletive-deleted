import { Download } from 'lucide-react'
import type { AppUpdateInfo } from '../../../shared/bridge'

type UpdateBannerProps = {
  info: AppUpdateInfo
  onDownload: () => void
  onDismiss: () => void
}

export function UpdateBanner({ info, onDownload, onDismiss }: UpdateBannerProps) {
  return (
    <div className="alert update" role="status">
      <Download size={18} aria-hidden="true" />
      <span><strong>Version {info.latestVersion} is available.</strong> You’re using {info.currentVersion}.</span>
      <button className="update-primary" type="button" onClick={onDownload}>{info.downloadUrl ? 'Download update' : 'View release'}</button>
      <button type="button" onClick={onDismiss}>Remind me later</button>
    </div>
  )
}

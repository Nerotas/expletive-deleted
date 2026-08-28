declare module 'lucide-react' {
  import type { ComponentType, SVGProps } from 'react'

  type Icon = ComponentType<SVGProps<SVGSVGElement> & { size?: number | string }>
  export const AlertCircle: Icon
  export const ArchiveIcon: Icon
  export const BookOpen: Icon
  export const Check: Icon
  export const CircleStop: Icon
  export const FolderOpen: Icon
  export const ListVideo: Icon
  export const LoaderCircle: Icon
  export const MoonIcon: Icon
  export const Play: Icon
  export const RefreshCw: Icon
  export const RotateCcw: Icon
  export const Save: Icon
  export const Settings: Icon
  export const ShieldCheck: Icon
  export const SunIcon: Icon
}

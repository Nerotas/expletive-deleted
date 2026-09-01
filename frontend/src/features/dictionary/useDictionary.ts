import { useEffect, useState } from 'react'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { desktopClient, type DesktopClient } from '../../services/desktop-client'
import type {
  DictionaryAction,
  DictionarySort,
  DictionaryTarget,
  ReviewResult,
  SortDirection,
} from '../../types/domain'
import { errorMessage } from '../../utils/format'

const DICTIONARY_LOAD_TIMEOUT_MS = 15_000
const DICTIONARY_PAGE_SIZE = 25

function withLoadTimeout<T>(request: Promise<T>) {
  return new Promise<T>((resolve, reject) => {
    const timeout = globalThis.setTimeout(() => {
      reject(new Error('The censor dictionary did not respond. Retry, or restart the desktop application.'))
    }, DICTIONARY_LOAD_TIMEOUT_MS)
    request.then(resolve, reject).finally(() => globalThis.clearTimeout(timeout))
  })
}

type DictionaryOptions = {
  client?: DesktopClient
  enabled?: boolean
  onError: (message: string) => void
  onNotice: (message: string) => void
}

export function useDictionary({
  client = desktopClient,
  enabled = true,
  onError,
  onNotice,
}: DictionaryOptions) {
  const [review, setReview] = useState<ReviewResult | null>(null)
  const [target, setTarget] = useState<DictionaryTarget>('exclude')
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [sort, setSortState] = useState<DictionarySort>('value')
  const [direction, setDirection] = useState<SortDirection>('asc')
  const [censoredWordsRevealed, setCensoredWordsRevealed] = useState(false)
  const queryClient = useQueryClient()

  const infoQuery = useQuery({
    queryKey: ['dictionary', 'info'],
    queryFn: () => withLoadTimeout(client.getDictionaryInfo()),
    enabled,
  })
  const entriesQuery = useQuery({
    queryKey: ['dictionary', 'entries', target, page, search, sort, direction],
    queryFn: () => withLoadTimeout(target === 'exclude'
      ? client.getDictionaryExclusions(page, DICTIONARY_PAGE_SIZE, sort, direction, search)
      : client.getCensoredWords(page, DICTIONARY_PAGE_SIZE, sort, direction, search)),
    enabled: enabled && (target === 'exclude' || censoredWordsRevealed),
    placeholderData: keepPreviousData,
  })
  const discoveredQuery = useQuery({
    queryKey: ['dictionary', 'discovered'],
    queryFn: () => client.getDiscoveredWords(),
    enabled,
  })

  useEffect(() => {
    const error = infoQuery.error ?? entriesQuery.error ?? discoveredQuery.error
    if (error) onError(errorMessage(error))
  }, [discoveredQuery.error, entriesQuery.error, infoQuery.error, onError])

  const refreshDictionary = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['dictionary', 'info'] }),
      queryClient.invalidateQueries({ queryKey: ['dictionary', 'entries'] }),
      queryClient.invalidateQueries({ queryKey: ['dictionary', 'discovered'] }),
    ])
  }

  const updateMutation = useMutation({
    mutationFn: ({ target: destination, word, action }: {
      target: DictionaryTarget
      word: string
      action: DictionaryAction
    }) => client.updateDictionary(action, destination, word),
    onSuccess: async (_summary, { target: destination, word, action }) => {
      setReview((current) => current ? {
        ...current,
        candidates: current.candidates.filter(
          (candidate) => candidate.word !== word.trim().toLowerCase(),
        ),
      } : null)
      await refreshDictionary()
      onNotice(
        action === 'add'
          ? `Added ${word} to ${destination === 'censor' ? 'censored words' : 'exclusions'}`
          : `Removed ${word}`,
      )
    },
    onError: (reason) => onError(errorMessage(reason)),
  })

  const reviewMutation = useMutation({
    mutationFn: (source: string) => client.getReview(source),
    onSuccess: setReview,
    onError: (reason) => onError(errorMessage(reason)),
  })

  const replaceMutation = useMutation({
    mutationFn: ({ operation, source }: { operation: 'restore' | 'import'; source?: string }) =>
      operation === 'restore'
        ? client.restoreDictionaryDefaults()
        : client.importDictionary(source!),
    onSuccess: async (_summary, { operation }) => {
      setPage(1)
      await refreshDictionary()
      onNotice(operation === 'restore' ? 'Restored the default dictionary' : 'Imported dictionary')
    },
    onError: (reason) => onError(errorMessage(reason)),
  })

  const exportMutation = useMutation({
    mutationFn: (destination: string) => client.exportDictionary(destination),
    onSuccess: ({ path }) => onNotice(`Exported dictionary to ${path}`),
    onError: (reason) => onError(errorMessage(reason)),
  })

  return {
    info: infoQuery.data ?? null,
    entries: entriesQuery.data ?? null,
    discovered: discoveredQuery.data?.words ?? [],
    review,
    target,
    page,
    search,
    sort,
    direction,
    censoredWordsRevealed,
    tableLoading: entriesQuery.isLoading,
    tableFailed: entriesQuery.isError,
    busy: infoQuery.isFetching || entriesQuery.isFetching || updateMutation.isPending
      || reviewMutation.isPending || replaceMutation.isPending || exportMutation.isPending,
    reload: refreshDictionary,
    showExclusions: () => {
      setTarget('exclude')
      setPage(1)
    },
    revealCensoredWords: () => {
      setCensoredWordsRevealed(true)
      setTarget('censor')
      setPage(1)
    },
    setPage,
    setSearch: (value: string) => {
      setSearch(value)
      setPage(1)
    },
    setSort: (value: DictionarySort) => {
      if (sort === value) setDirection((current) => current === 'asc' ? 'desc' : 'asc')
      else {
        setSortState(value)
        setDirection('asc')
      }
      setPage(1)
    },
    updateDictionary: async (
      destination: DictionaryTarget,
      word: string,
      action: DictionaryAction = 'add',
    ) => {
      await updateMutation.mutateAsync({ target: destination, word, action }).catch(() => undefined)
    },
    restoreDefaults: async () => {
      await replaceMutation.mutateAsync({ operation: 'restore' }).catch(() => undefined)
    },
    importDictionary: async () => {
      const source = await client.selectDictionaryImport()
      if (source) await replaceMutation.mutateAsync({ operation: 'import', source }).catch(() => undefined)
    },
    exportDictionary: async () => {
      const destination = await client.selectDictionaryExport()
      if (destination) await exportMutation.mutateAsync(destination).catch(() => undefined)
    },
    openReview: async (source: string) => {
      await reviewMutation.mutateAsync(source).catch(() => undefined)
    },
    closeReview: () => setReview(null),
  }
}

export type DictionaryController = ReturnType<typeof useDictionary>

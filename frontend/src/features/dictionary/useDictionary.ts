import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { desktopClient, type DesktopClient } from '../../services/desktop-client'
import type { DictionaryAction, DictionaryTarget, ReviewResult } from '../../types/domain'
import { errorMessage } from '../../utils/format'

const DICTIONARY_LOAD_TIMEOUT_MS = 15_000

function loadDictionary(client: DesktopClient) {
  return new Promise<Awaited<ReturnType<DesktopClient['getDictionary']>>>((resolve, reject) => {
    const timeout = globalThis.setTimeout(() => {
      reject(new Error('The censor dictionary did not respond. Retry, or restart the desktop application.'))
    }, DICTIONARY_LOAD_TIMEOUT_MS)

    client.getDictionary().then(resolve, reject).finally(() => globalThis.clearTimeout(timeout))
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
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['dictionary'],
    queryFn: () => loadDictionary(client),
    enabled,
  })

  useEffect(() => {
    if (query.error) onError(errorMessage(query.error))
  }, [onError, query.error])

  const updateMutation = useMutation({
    mutationFn: ({ target, word, action }: {
      target: DictionaryTarget
      word: string
      action: DictionaryAction
    }) => client.updateDictionary(action, target, word),
    onSuccess: (dictionary, { target, word, action }) => {
      queryClient.setQueryData(['dictionary'], dictionary)
      setReview((current) => current ? {
        ...current,
        candidates: current.candidates.filter(
          (candidate) => candidate.word !== word.trim().toLowerCase(),
        ),
      } : null)
      onNotice(
        action === 'add'
          ? `Added ${word} to ${target === 'censor' ? 'censored words' : 'exclusions'}`
          : `Removed ${word}`,
      )
      return dictionary
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
    onSuccess: (dictionary, { operation }) => {
      queryClient.setQueryData(['dictionary'], dictionary)
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
    // The query cache is the single renderer snapshot. Mutation responses update
    // it above, while a later reload can still reveal policy-file changes.
    dictionary: query.data ?? null,
    review,
    loading: query.isLoading,
    loadFailed: query.isError,
    busy: query.isFetching || updateMutation.isPending || reviewMutation.isPending
      || replaceMutation.isPending || exportMutation.isPending,
    reload: async () => {
      await query.refetch()
    },
    updateDictionary: async (
      target: DictionaryTarget,
      word: string,
      action: DictionaryAction = 'add',
    ) => {
      await updateMutation.mutateAsync({ target, word, action }).catch(() => undefined)
    },
    restoreDefaults: async () => {
      await replaceMutation.mutateAsync({ operation: 'restore' }).catch(() => undefined)
    },
    importDictionary: async () => {
      const source = await client.selectDictionaryImport()
      if (source) {
        await replaceMutation.mutateAsync({ operation: 'import', source }).catch(() => undefined)
      }
    },
    exportDictionary: async () => {
      const destination = await client.selectDictionaryExport()
      if (destination) {
        await exportMutation.mutateAsync(destination).catch(() => undefined)
      }
    },
    openReview: async (source: string) => {
      await reviewMutation.mutateAsync(source).catch(() => undefined)
    },
    closeReview: () => setReview(null),
  }
}

export type DictionaryController = ReturnType<typeof useDictionary>

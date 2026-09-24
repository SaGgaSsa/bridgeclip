import { create } from 'zustand'
import { errorMessage } from '../lib/utils'
import { getApi } from '../lib/ipc'
import type { ClipSettings, ToolStatus } from '../../preload/index'
import { useDraftStore } from './use-draft-store'

export const SETTINGS_DEFAULTS = {
  transcriptionProvider: 'local',
  plannerProvider: 'opencode',
  opencodeModel: 'opencode/muse-spark-1.3-contributor-free',
  opencodeCommand: 'opencode',
  localWhisperModel: 'small',
  opencodeTimeoutSeconds: 300
} as const

interface SettingsState extends ClipSettings {
  loaded: boolean
  saving: boolean
  toolStatus: ToolStatus | null
  checkingTools: boolean
  toolError: string | null
  load: () => Promise<void>
  save: (settings: Partial<ClipSettings>) => Promise<void>
  replaceApiKey: (key: 'openrouterApiKey' | 'zernioApiKey', value: string) => Promise<void>
  checkTools: () => Promise<void>
}

// Queue writes so each partial update merges with the last successful save.
let saveQueue: Promise<void> = Promise.resolve()
let pendingSaves = 0
let latestToolCheck = 0

export const useSettingsStore = create<SettingsState>((set, get) => ({
  openrouterConfigured: false,
  zernioConfigured: false,
  outputDirectory: '',
  pythonPath: 'python3',
  customVocabulary: '',
  transcriptionProvider: SETTINGS_DEFAULTS.transcriptionProvider,
  plannerProvider: SETTINGS_DEFAULTS.plannerProvider,
  opencodeModel: SETTINGS_DEFAULTS.opencodeModel,
  opencodeCommand: SETTINGS_DEFAULTS.opencodeCommand,
  localWhisperModel: SETTINGS_DEFAULTS.localWhisperModel,
  opencodeTimeoutSeconds: SETTINGS_DEFAULTS.opencodeTimeoutSeconds,
  loaded: false,
  saving: false,
  toolStatus: null,
  checkingTools: false,
  toolError: null,

  load: async () => {
    const settings = await getApi().settings.load()
    set({ ...pickSettings(settings), loaded: true })
  },

  save: (updates) => {
    const patch = { ...updates }
    pendingSaves += 1
    set({ saving: true })
    const task = saveQueue.then(async () => {
      const merged: ClipSettings = { ...pickSettings(get()), ...patch }
      const saved = await getApi().settings.save(merged)
      set({ ...pickSettings(saved), loaded: true })
    })
    saveQueue = task.catch(() => {})
    return task.finally(() => {
      pendingSaves -= 1
      set({ saving: pendingSaves > 0 })
    })
  },

  replaceApiKey: (key, value) => {
    pendingSaves += 1
    set({ saving: true })
    const task = saveQueue.then(async () => {
      const saved = await getApi().settings.replaceApiKey(key, value)
      set({ ...pickSettings(saved), loaded: true })
    })
    saveQueue = task.catch(() => {})
    return task.finally(() => {
      pendingSaves -= 1
      set({ saving: pendingSaves > 0 })
    })
  },

  checkTools: async () => {
    const request = ++latestToolCheck
    set({ checkingTools: true, toolError: null })
    try {
      const status = await getApi().system.checkTools()
      if (request === latestToolCheck) set({ toolStatus: status })
    } catch (err) {
      if (request === latestToolCheck) {
        set({ toolStatus: null, toolError: errorMessage(err, 'Could not check required tools. Try again in Settings.') })
      }
    } finally {
      if (request === latestToolCheck) set({ checkingTools: false })
    }
  }
}))

function pickSettings(s: ClipSettings): ClipSettings {
  return {
    openrouterConfigured: s.openrouterConfigured,
    zernioConfigured: s.zernioConfigured,
    outputDirectory: s.outputDirectory,
    pythonPath: s.pythonPath,
    customVocabulary: s.customVocabulary,
    transcriptionProvider: s.transcriptionProvider ?? SETTINGS_DEFAULTS.transcriptionProvider,
    plannerProvider: s.plannerProvider ?? SETTINGS_DEFAULTS.plannerProvider,
    opencodeModel: s.opencodeModel ?? SETTINGS_DEFAULTS.opencodeModel,
    opencodeCommand: s.opencodeCommand ?? SETTINGS_DEFAULTS.opencodeCommand,
    localWhisperModel: s.localWhisperModel ?? SETTINGS_DEFAULTS.localWhisperModel,
    opencodeTimeoutSeconds: s.opencodeTimeoutSeconds ?? SETTINGS_DEFAULTS.opencodeTimeoutSeconds
  }
}

export type SetupState = { ready: boolean; missingKeys: string[]; toolsOk: boolean | null }

export interface SetupInputs {
  openrouterConfigured: boolean
  transcriptionProvider: 'local' | 'openrouter'
  plannerProvider: 'opencode' | 'openrouter'
  toolStatus: ToolStatus | null
  toolError: string | null
  checkingTools: boolean
  aspectRatio: string
  layoutStyle: string
  layoutVision: boolean
}

/** Pure setup derivation: OpenRouter key only when a chosen provider or the
 *  current draft's AI layout vision (9:16 + auto + toggle) needs it. */
export function deriveSetupState(inputs: SetupInputs): SetupState {
  const visionActive = inputs.aspectRatio === '9:16' && inputs.layoutStyle === 'auto' && inputs.layoutVision === true
  const needsOpenrouter =
    inputs.transcriptionProvider === 'openrouter' || inputs.plannerProvider === 'openrouter' || visionActive
  const missingKeys = [needsOpenrouter && !inputs.openrouterConfigured && 'OpenRouter'].filter(Boolean) as string[]
  const toolsOk = inputs.toolError
    ? false
    : inputs.toolStatus
      ? inputs.toolStatus.python &&
        inputs.toolStatus.pythonDeps &&
        inputs.toolStatus.ffmpeg &&
        inputs.toolStatus.ffprobe &&
        inputs.toolStatus.ytdlp &&
        inputs.toolStatus.engine &&
        inputs.toolStatus.bridgeRunner &&
        (inputs.transcriptionProvider === 'local' ? inputs.toolStatus.fasterWhisper : true) &&
        (inputs.plannerProvider === 'opencode' ? inputs.toolStatus.opencode : true)
      : null
  return { ready: missingKeys.length === 0 && toolsOk === true && !inputs.checkingTools, missingKeys, toolsOk }
}

/** Whether a clip job can start: keyless local path unless a provider or AI vision needs OpenRouter. */
export function useSetupState(): SetupState {
  const openrouterConfigured = useSettingsStore((s) => s.openrouterConfigured)
  const transcriptionProvider = useSettingsStore((s) => s.transcriptionProvider)
  const plannerProvider = useSettingsStore((s) => s.plannerProvider)
  const toolStatus = useSettingsStore((s) => s.toolStatus)
  const toolError = useSettingsStore((s) => s.toolError)
  const checkingTools = useSettingsStore((s) => s.checkingTools)
  const aspectRatio = useDraftStore((s) => s.aspectRatio)
  const layoutStyle = useDraftStore((s) => s.layoutStyle)
  const layoutVision = useDraftStore((s) => s.layoutVision)
  return deriveSetupState({ openrouterConfigured, transcriptionProvider, plannerProvider, toolStatus, toolError, checkingTools, aspectRatio, layoutStyle, layoutVision })
}

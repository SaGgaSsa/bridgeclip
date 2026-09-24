import { useEffect, useState, type ReactNode } from 'react'
import { ArrowUpRight, KeyRound, Loader2, Plus, RefreshCw, Share2, UserPlus, WifiOff } from 'lucide-react'
import { useSettingsStore } from '../store/use-settings-store'
import { useAccountsStore, type AccountsNotice } from '../store/use-accounts-store'
import { useApiKeyDrafts } from '../hooks/use-api-key-drafts'
import { getApi } from '../lib/ipc'
import { cn } from '../lib/utils'
import { PROVIDER_LINKS, ZERNIO_LINKS } from '../config/brand'
import { isValidProfileName, isZernioPlatform, ZERNIO_PLATFORMS, ZERNIO_PROFILE_NAME_MAX, type ZernioAccount, type ZernioPlatform } from '../../shared/zernio'
import { ApiKeyInput } from '../components/ApiKeyInput'
import { PLATFORM_INFO, PlatformIcon, platformName } from '../components/PlatformIcon'
import { PostsPanel } from '../components/PostsPanel'
import { PageHeader } from '../components/ui/PageHeader'
import { Page as PageColumn } from '../components/ui/Page'
import { Panel, PanelHeader } from '../components/ui/Panel'
import { Button } from '../components/ui/Button'
import { Badge, StatusDot } from '../components/ui/Badge'
import { Callout } from '../components/ui/Callout'
import { IconTile } from '../components/ui/IconTile'
import { Field, Select, TextInput } from '../components/ui/Field'
import { Skeleton } from '../components/ui/Skeleton'
import { ProgressBar } from '../components/ui/ProgressBar'
import type { Page } from '../components/Sidebar'

const TITLE = 'Accounts'
const EYEBROW = 'Publishing'
const DESCRIPTION = 'Connect and manage your social accounts through Zernio.'
/** Opening the page re-reads Zernio only when the shown data is older than this. */
const REFRESH_ON_OPEN_AFTER_MS = 30_000

function openLink(url: string): void {
  void getApi().shell.openPath(url).catch(() => {})
}

export function AccountsPage({ onNavigate }: { onNavigate: (page: Page) => void }): React.JSX.Element {
  const configured = useSettingsStore((s) => s.zernioConfigured)
  return (
    <PageColumn width="narrow">
      {configured ? <ConnectedAccounts onNavigate={onNavigate} /> : <ZernioSetup />}
    </PageColumn>
  )
}

function ZernioSetup(): React.JSX.Element {
  const keys = useApiKeyDrafts()

  return (
    <>
      <PageHeader eyebrow={EYEBROW} title={TITLE} description={DESCRIPTION} />
      <Panel padded={false} className="mt-5 overflow-hidden">
        <div className="relative p-5">
          <PanelHeader
            icon={<IconTile tone="accent" size="lg"><Share2 /></IconTile>}
            title="Connect with Zernio"
            description="BridgeClip uses your Zernio API key to manage connections. Platform sign-in happens in your browser through Zernio."
          />
          <ol className="mt-5 space-y-5">
            <SetupStep
              step={1}
              title="Create a free Zernio account"
              description="The first two connected accounts are free on most platforms; X may require a card."
              action={
                <Button size="sm" trailingIcon={<ArrowUpRight className="h-3.5 w-3.5" />} onClick={() => openLink(ZERNIO_LINKS.signup)}>
                  Sign up
                </Button>
              }
            />
            <SetupStep
              step={2}
              title="Create an API key"
              description="In Zernio, open API keys and create one. Copy it right away: Zernio only shows it once."
              action={
                <Button size="sm" trailingIcon={<ArrowUpRight className="h-3.5 w-3.5" />} onClick={() => openLink(PROVIDER_LINKS.zernio)}>
                  Open API keys
                </Button>
              }
            />
            <SetupStep step={3} title="Paste your key" last>
              <ApiKeyInput
                label="Zernio API key"
                value={keys.drafts.zernioApiKey}
                onChange={(v) => keys.setDraft('zernioApiKey', v)}
                onBlur={() => void keys.persist()}
                placeholder="sk_…"
                description="Encrypted with your system keychain. You can change it later in Settings."
              />
              {keys.error && <p role="alert" className="mt-2 text-xs text-danger">{keys.error}</p>}
            </SetupStep>
          </ol>
        </div>
        <div className="relative flex items-center gap-3 border-t border-white/[0.06] bg-black/[0.12] px-5 py-3">
          <div className="flex -space-x-1.5">
            {ZERNIO_PLATFORMS.map((platform) => (
              <PlatformIcon key={platform} platform={platform} className="h-7 w-7 rounded-full ring-2 ring-canvas/60 [&_svg]:h-3.5 [&_svg]:w-3.5" />
            ))}
          </div>
          <p className="text-xs text-ink-muted">Post and schedule clips to {ZERNIO_PLATFORMS.length} platforms from one place.</p>
        </div>
      </Panel>
    </>
  )
}

function SetupStep({
  step,
  title,
  description,
  action,
  last = false,
  children
}: {
  step: number
  title: string
  description?: string
  action?: ReactNode
  last?: boolean
  children?: ReactNode
}): React.JSX.Element {
  return (
    <li className="relative flex gap-3">
      {/* The thread that joins one step's lens to the next. */}
      {!last && (
        <span aria-hidden className="absolute bottom-[-24px] left-[15.5px] top-10 w-px bg-white/[0.1]" />
      )}
      <span className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/[0.1] font-mono text-xs font-medium tabular text-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.22),inset_0_0_0_1px_rgb(255_255_255/0.12),0_4px_12px_-4px_rgb(0_0_0/0.6)]">
        {step}
      </span>
      <div className="min-w-0 flex-1 pt-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink">{title}</p>
            {description && <p className="mt-1 text-sm leading-relaxed text-ink-muted">{description}</p>}
          </div>
          {action}
        </div>
        {children && <div className="mt-3">{children}</div>}
      </div>
    </li>
  )
}

function ConnectedAccounts({ onNavigate }: { onNavigate: (page: Page) => void }): React.JSX.Element {
  const [creatingProfile, setCreatingProfile] = useState(false)
  const [newProfileName, setNewProfileName] = useState('')
  const [newProfilePlatform, setNewProfilePlatform] = useState<ZernioPlatform>('youtube')
  const {
    profiles,
    accounts,
    profileId,
    syncedAt,
    loaded,
    loading,
    error,
    connecting,
    disconnecting,
    notice,
    hydrate,
    load,
    refreshOnFocus,
    setProfile,
    connect,
    cancelConnect,
    disconnect,
    dismissNotice
  } = useAccountsStore()

  // Cached accounts show at once; Zernio is only asked again when they're old.
  useEffect(() => {
    void hydrate().then(() => {
      const state = useAccountsStore.getState()
      if (!state.loading && Date.now() - Math.max(state.syncedAt, state.lastAttemptAt) > REFRESH_ON_OPEN_AFTER_MS) void state.load()
    })
  }, [hydrate])

  // Coming back from the browser is the moment an account appears.
  useEffect(() => {
    window.addEventListener('focus', refreshOnFocus)
    return () => window.removeEventListener('focus', refreshOnFocus)
  }, [refreshOnFocus])

  const profile = profiles.find((p) => p.id === profileId)
  const inProfile = accounts.filter((a) => a.profileId === profileId)
  const byPlatform = new Map(inProfile.map((a) => [a.platform, a]))
  const available = ZERNIO_PLATFORMS.filter((platform) => !byPlatform.has(platform))
  // Accounts that need a sign-in or a look come first, then Zernio's platform order.
  const order = (platform: string): number => {
    const index = (ZERNIO_PLATFORMS as readonly string[]).indexOf(platform)
    return index === -1 ? ZERNIO_PLATFORMS.length : index
  }
  const connected = [...inProfile].sort((a, b) =>
    Number(accountHealth(b) !== 'ok') - Number(accountHealth(a) !== 'ok') || order(a.platform) - order(b.platform))
  const attention = connected.filter((a) => accountHealth(a) !== 'ok').length
  const hasData = syncedAt > 0
  const busy = Boolean(connecting) || Boolean(disconnecting)
  const profileNameValid = isValidProfileName(newProfileName)
  const connectInNewProfile = (event: React.FormEvent<HTMLFormElement>): void => {
    event.preventDefault()
    if (!profileNameValid || busy) return
    void connect(newProfilePlatform, { newProfileName: newProfileName.trim() })
    setCreatingProfile(false)
    setNewProfileName('')
  }
  const openNoticeAction = (action: AccountsNotice['action']): void => {
    if (action === 'billing') openLink(ZERNIO_LINKS.billing)
    else if (action === 'settings') onNavigate('settings')
  }

  const connectedCount = inProfile.filter((a) => isZernioPlatform(a.platform) && accountHealth(a) === 'ok').length

  return (
    <>
      <PageHeader
        eyebrow={EYEBROW}
        title={TITLE}
        description={DESCRIPTION}
        actions={
          <>
            <Button
              size="sm"
              variant="secondary"
              icon={creatingProfile ? undefined : <Plus className="h-3.5 w-3.5" />}
              onClick={() => setCreatingProfile((open) => !open)}
              disabled={busy}
              aria-expanded={creatingProfile}
              aria-controls="new-zernio-profile-form"
            >
              {creatingProfile ? 'Close' : 'New profile'}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              iconOnly
              aria-label="Refresh accounts"
              title="Refresh"
              onClick={() => void load()}
              disabled={loading}
              icon={<RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />}
            />
          </>
        }
      />

      <div className="mt-5 space-y-4">
        {notice && <NoticeBar notice={notice} onDismiss={dismissNotice} onAction={openNoticeAction} />}

        {creatingProfile && (
          <Panel className="animate-pop-in">
            <PanelHeader
              icon={<IconTile tone="accent"><UserPlus /></IconTile>}
              title="Connect in a new profile"
              description="Give the profile a name, then choose the first platform to connect. You can add more platforms after sign-in."
            />
            <form id="new-zernio-profile-form" className="mt-4 space-y-4" onSubmit={connectInNewProfile}>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field
                  label="Profile name"
                  htmlFor="zernio-new-profile-name"
                  hint={<span id="zernio-new-profile-hint">Use 1–{ZERNIO_PROFILE_NAME_MAX} characters.</span>}
                >
                  <TextInput
                    id="zernio-new-profile-name"
                    type="text"
                    value={newProfileName}
                    onChange={(event) => setNewProfileName(event.target.value)}
                    maxLength={ZERNIO_PROFILE_NAME_MAX}
                    required
                    autoFocus
                    placeholder="e.g. My channel"
                    aria-describedby="zernio-new-profile-hint"
                  />
                </Field>
                <Field label="First platform" htmlFor="zernio-new-profile-platform">
                  <Select
                    id="zernio-new-profile-platform"
                    value={newProfilePlatform}
                    onChange={(event) => setNewProfilePlatform(event.target.value as ZernioPlatform)}
                  >
                    {ZERNIO_PLATFORMS.map((platform) => <option key={platform} value={platform}>{platformName(platform)}</option>)}
                  </Select>
                </Field>
              </div>
              <div className="flex justify-end gap-2">
                <Button type="button" size="sm" variant="ghost" onClick={() => setCreatingProfile(false)}>Cancel</Button>
                <Button type="submit" size="sm" variant="primary" disabled={!profileNameValid || busy}>Create and connect</Button>
              </div>
            </form>
          </Panel>
        )}

        {error && (!hasData || error.kind === 'auth') ? (
          <Callout
            tone="danger"
            icon={error.kind === 'auth' ? <KeyRound /> : undefined}
            stacked
            action={
              <>
                <Button size="sm" onClick={() => void load()} loading={loading}>
                  Try again
                </Button>
                <Button size="sm" variant="ghost" onClick={() => onNavigate('settings')}>
                  Open Settings
                </Button>
              </>
            }
          >
            {error.message}
            {hasData && <p className="mt-1 text-xs text-ink-muted">Showing the accounts from {syncedAgo(syncedAt)}.</p>}
          </Callout>
        ) : error ? (
          <StaleNotice error={error.message} offline={error.kind === 'offline'} syncedAt={syncedAt} loading={loading} onRetry={() => void load()} />
        ) : null}

        {!hasData && !error && (loading || !loaded) && <LoadingRows />}

        {hasData && (
          <>
            <Panel>
              <div className="flex flex-wrap items-center gap-3">
                <span aria-hidden className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/[0.08] text-base font-semibold text-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.18),inset_0_0_0_1px_rgb(255_255_255/0.1)]">
                  {(profile?.name ?? '?').charAt(0).toUpperCase()}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="eyebrow">Zernio profile</p>
                  {profiles.length > 1 ? (
                    <Select
                      aria-label="Zernio profile"
                      value={profileId ?? ''}
                      onChange={(e) => setProfile(e.target.value)}
                      disabled={busy}
                      className="mt-1 max-w-[280px]"
                    >
                      {profiles.map((p) => {
                        const count = accounts.filter((a) => a.profileId === p.id).length
                        return (
                          <option key={p.id} value={p.id}>
                            {p.name}
                            {count ? ` (${count})` : ''}
                          </option>
                        )
                      })}
                    </Select>
                  ) : (
                    <p className="mt-0.5 truncate text-base font-semibold text-ink">{profile?.name ?? 'Default'}</p>
                  )}
                </div>
                <SyncedLabel syncedAt={syncedAt} stale={Boolean(error)} />
              </div>
              <div className="mt-4 flex items-center gap-3">
                <ProgressBar value={(connectedCount / ZERNIO_PLATFORMS.length) * 100} className="flex-1" />
                <p className="shrink-0 text-xs text-ink-muted">
                  <span className="font-mono tabular text-ink">{connectedCount}/{ZERNIO_PLATFORMS.length}</span> platforms ready
                  {attention > 0 && <span className="text-warning"> · {attention} need{attention === 1 ? 's' : ''} attention</span>}
                </p>
              </div>
              {profile?.isOverLimit && (
                <Callout tone="warning" className="mt-3" action={<Button size="sm" trailingIcon={<ArrowUpRight className="h-3.5 w-3.5" />} onClick={() => openLink(ZERNIO_LINKS.billing)}>Zernio billing</Button>}>
                  This profile is over your Zernio plan’s profile limit, so its accounts can’t post.
                </Callout>
              )}
            </Panel>

            {connected.length > 0 && (
              <Panel padded={false} className="overflow-hidden">
                <PanelHeader
                  className="p-4 pb-3"
                  title="Connected"
                  description="One account per platform. Connecting a platform again replaces its account."
                />
                <ul className="divide-y divide-white/[0.06] border-t border-white/[0.06]">
                  {connected.map((account) => (
                    <PlatformRow
                      key={account.id}
                      platform={account.platform}
                      account={account}
                      connecting={connecting?.platform === account.platform}
                      busy={busy}
                      disconnecting={disconnecting === account.id}
                      onConnect={isZernioPlatform(account.platform) ? (reconnect) => void connect(account.platform as ZernioPlatform, { reconnect }) : undefined}
                      onCancel={cancelConnect}
                      onDisconnect={(id) => void disconnect(id)}
                    />
                  ))}
                </ul>
              </Panel>
            )}

            {available.length > 0 && (
              <Panel>
                <PanelHeader
                  icon={<IconTile><Share2 /></IconTile>}
                  title={connected.length ? 'Add a platform' : 'Connect your first platform'}
                  description="Sign-in opens in your browser. Come back here when you’re done."
                />
                <ul className="mt-4 grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(220px,1fr))]">
                  {available.map((platform) => (
                    <PlatformTile
                      key={platform}
                      platform={platform}
                      connecting={connecting?.platform === platform}
                      busy={busy}
                      onConnect={() => void connect(platform, { reconnect: false })}
                      onCancel={cancelConnect}
                    />
                  ))}
                </ul>
              </Panel>
            )}
          </>
        )}

        <PostsPanel onNavigate={onNavigate} />

        <p className="px-1 text-xs text-ink-subtle">
          Zernio bills per connected account, and your first 2 are free.{' '}
          <button
            onClick={() => openLink(ZERNIO_LINKS.pricing)}
            className="inline-flex items-center gap-0.5 text-ink-muted transition-colors hover:text-ink"
          >
            Pricing
            <ArrowUpRight className="h-3 w-3" />
          </button>
        </p>
      </div>
    </>
  )
}

type AccountHealth = 'ok' | 'sign-in' | 'unhealthy'

function accountHealth(account: ZernioAccount): AccountHealth {
  if (account.needsReconnect || !account.isActive) return 'sign-in'
  if (account.health === 'error' || account.canPost === false) return 'unhealthy'
  return 'ok'
}

/** A platform with no account in this profile yet. */
function PlatformTile({
  platform,
  connecting,
  busy,
  onConnect,
  onCancel
}: {
  platform: ZernioPlatform
  connecting: boolean
  busy: boolean
  onConnect: () => void
  onCancel: () => void
}): React.JSX.Element {
  const name = platformName(platform)
  const note = PLATFORM_INFO[platform].note
  return (
    <li
      data-platform={platform}
      data-state="disconnected"
      className={cn('glass-tile flex flex-col rounded-2xl p-3 transition-colors duration-150', connecting && 'glass-selected')}
    >
      <div className="flex items-center gap-2.5">
        <PlatformIcon platform={platform} className="h-8 w-8 rounded-lg" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-ink">{name}</span>
        {connecting && <Loader2 className="h-4 w-4 animate-spin text-accent-hover" aria-label="Waiting for your browser" />}
      </div>
      <p className={cn('mt-2 flex-1 text-2xs leading-relaxed', connecting ? 'text-accent-hover' : 'text-ink-subtle')}>
        {connecting ? `Finish signing in to ${name} in your browser…` : note ?? 'Ready to connect'}
      </p>
      <div className="mt-3">
        {connecting ? (
          <Button size="sm" variant="ghost" className="w-full" onClick={onCancel} aria-label={`Cancel connecting ${name}`}>
            Cancel
          </Button>
        ) : (
          <Button size="sm" className="w-full" icon={<Plus className="h-3.5 w-3.5" />} onClick={onConnect} disabled={busy} aria-label={`Connect ${name}`}>
            Connect
          </Button>
        )}
      </div>
    </li>
  )
}

/** "just now", "4 min ago", "3 h ago", or a date. */
function syncedAgo(syncedAt: number, now = Date.now()): string {
  const minutes = Math.floor((now - syncedAt) / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return new Date(syncedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/** Re-renders on an interval so relative times stay current (no network). */
function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(timer)
  }, [intervalMs])
  return now
}

function SyncedLabel({ syncedAt, stale }: { syncedAt: number; stale: boolean }): React.JSX.Element {
  const now = useNow(30_000)
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-2xs',
        stale ? 'bg-warning/[0.1] text-warning' : 'bg-white/[0.05] text-ink-subtle'
      )}
      data-testid="accounts-synced"
    >
      {stale ? 'Last synced' : 'Synced'} {syncedAgo(syncedAt, now)}
    </span>
  )
}

/** Refresh failed but cached accounts are on screen: say so quietly, without hiding them. */
function StaleNotice({
  error,
  offline,
  syncedAt,
  loading,
  onRetry
}: {
  error: string
  offline: boolean
  syncedAt: number
  loading: boolean
  onRetry: () => void
}): React.JSX.Element {
  const now = useNow(30_000)
  return (
    <Callout
      tone="warning"
      role="status"
      icon={offline ? <WifiOff /> : undefined}
      action={
        <Button size="sm" variant="ghost" onClick={onRetry} loading={loading}>
          Try again
        </Button>
      }
    >
      <p>
        {error} <span className="text-ink-muted">Showing accounts from {syncedAgo(syncedAt, now)}.</span>
      </p>
    </Callout>
  )
}

function LoadingRows(): React.JSX.Element {
  return (
    <Panel padded={false} className="overflow-hidden" aria-busy="true" aria-label="Loading your Zernio accounts">
      <div className="flex items-center gap-2.5 p-4 pb-4 text-sm text-ink-muted">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading your Zernio accounts…
      </div>
      <ul className="divide-y divide-white/[0.06] border-t border-white/[0.06]">
        {ZERNIO_PLATFORMS.slice(0, 4).map((platform) => (
          <li key={platform} className="flex items-center gap-3 px-4 py-3">
            <Skeleton className="h-10 w-10 rounded-xl" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-3 w-28" />
              <Skeleton className="h-2.5 w-48" />
            </div>
            <Skeleton className="h-[30px] w-20 rounded-full" />
          </li>
        ))}
      </ul>
    </Panel>
  )
}

function NoticeBar({
  notice,
  onDismiss,
  onAction
}: {
  notice: AccountsNotice
  onDismiss: () => void
  onAction: (action: AccountsNotice['action']) => void
}): React.JSX.Element {
  const failed = notice.tone === 'danger'
  return (
    <Callout
      tone={failed ? 'danger' : notice.tone === 'success' ? 'success' : 'info'}
      role={failed ? 'alert' : 'status'}
      data-testid="accounts-notice"
      onDismiss={onDismiss}
      action={
        notice.action === 'billing' ? (
          <Button size="sm" trailingIcon={<ArrowUpRight className="h-3.5 w-3.5" />} onClick={() => onAction('billing')}>
            Zernio billing
          </Button>
        ) : notice.action === 'settings' ? (
          <Button size="sm" onClick={() => onAction('settings')}>
            Open Settings
          </Button>
        ) : undefined
      }
    >
      {notice.text}
    </Callout>
  )
}

function accountLabel(account: ZernioAccount): string {
  const handle = account.username ? `@${account.username}` : null
  if (account.displayName && handle && account.displayName.replace(/^@/, '') !== account.username) {
    return `${account.displayName} · ${handle}`
  }
  return handle ?? account.displayName ?? 'Connected account'
}

interface PlatformRowProps {
  platform: string
  account?: ZernioAccount
  connecting: boolean
  busy: boolean
  disconnecting: boolean
  /** `reconnect` asks Zernio for a fresh sign-in on the connected account. */
  onConnect?: (reconnect: boolean) => void
  onCancel?: () => void
  onDisconnect: (accountId: string) => void
}

function PlatformRow({
  platform,
  account,
  connecting,
  busy,
  disconnecting,
  onConnect,
  onCancel,
  onDisconnect
}: PlatformRowProps): React.JSX.Element {
  const [confirming, setConfirming] = useState(false)
  const [confirmingReconnect, setConfirmingReconnect] = useState(false)
  const name = platformName(platform)
  const note = isZernioPlatform(platform) ? PLATFORM_INFO[platform as ZernioPlatform].note : undefined
  const health = account ? accountHealth(account) : 'ok'
  const needsSignIn = health === 'sign-in'
  const unhealthy = health === 'unhealthy'

  // An account disappearing (disconnected elsewhere) ends a pending confirmation.
  useEffect(() => {
    if (!account) {
      setConfirming(false)
      setConfirmingReconnect(false)
    }
  }, [account])

  let detail: ReactNode
  if (confirming && account) {
    detail = <span className="text-ink">Disconnect {accountLabel(account)}? This also removes it from your Zernio workspace.</span>
  } else if (confirmingReconnect && account) {
    detail = (
      <span role="alert" className="text-warning">
        Sign in as {accountLabel(account)}. A different TikTok account replaces it and permanently deletes its Zernio analytics, inbox and DM history. A renamed handle may also be treated as different.
      </span>
    )
  } else if (connecting) {
    detail = (
      <span className="text-accent-hover">
        {account
          ? 'Finish in your browser. Sign in as the same account to keep its history.'
          : `Finish signing in to ${name} in your browser…`}
      </span>
    )
  } else if (account) {
    const issue = account.issue && (needsSignIn || unhealthy || account.health === 'warning') ? account.issue : null
    detail = (
      <span className="flex min-w-0 items-center gap-2">
        {!needsSignIn && !unhealthy && <StatusDot tone="success" />}
        <span className="truncate" title={issue ?? undefined}>
          {accountLabel(account)}
          {issue && <span className={needsSignIn || unhealthy ? 'text-ink-muted' : 'text-ink-subtle'}> · {issue}</span>}
        </span>
      </span>
    )
  } else {
    detail = note ?? 'Not connected'
  }

  return (
    <li
      className={cn(
        'flex items-center gap-3 px-4 py-3 transition-colors duration-150',
        confirming ? 'bg-danger/[0.04]' : confirmingReconnect ? 'bg-warning/[0.04]' : connecting ? 'bg-accent/[0.05]' : 'hover:bg-white/[0.02]'
      )}
      data-platform={platform}
      data-state={account ? (needsSignIn ? 'reconnect' : 'connected') : 'disconnected'}
    >
      <PlatformIcon platform={platform} className={cn('h-10 w-10', !account && !connecting && 'opacity-70')} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-ink">{name}</span>
          {account?.needsReconnect ? (
            <Badge tone="warning">Reconnect needed</Badge>
          ) : account && !account.isActive ? (
            <Badge tone="warning">Inactive</Badge>
          ) : unhealthy ? (
            <Badge tone="warning">Needs attention</Badge>
          ) : null}
        </div>
        <div className="mt-1 text-xs text-ink-muted" data-selectable>
          {detail}
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-1.5">
        {confirming && account ? (
          <>
            <Button size="sm" variant="ghost" onClick={() => setConfirming(false)} disabled={disconnecting}>
              Cancel
            </Button>
            <Button
              size="sm"
              variant="danger"
              loading={disconnecting}
              aria-label={`Confirm disconnecting ${name}`}
              onClick={() => {
                onDisconnect(account.id)
                setConfirming(false)
              }}
            >
              Disconnect
            </Button>
          </>
        ) : confirmingReconnect && account ? (
          <>
            <Button size="sm" variant="ghost" onClick={() => setConfirmingReconnect(false)}>Cancel</Button>
            <Button size="sm" onClick={() => { setConfirmingReconnect(false); onConnect?.(true) }} aria-label={`Confirm reconnecting ${name}`}>
              Continue
            </Button>
          </>
        ) : connecting ? (
          <>
            <Loader2 className="mr-1 h-4 w-4 animate-spin text-accent-hover" aria-label="Waiting for your browser" />
            <Button size="sm" variant="ghost" onClick={onCancel} aria-label={`Cancel connecting ${name}`}>
              Cancel
            </Button>
          </>
        ) : account ? (
          <>
            {onConnect && (
              <Button
                size="sm"
                variant={needsSignIn || unhealthy ? 'secondary' : 'ghost'}
                onClick={() => platform === 'tiktok' ? setConfirmingReconnect(true) : onConnect(true)}
                disabled={busy}
                aria-label={`Reconnect ${name}`}
              >
                Reconnect
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setConfirming(true)}
              disabled={busy}
              loading={disconnecting}
              aria-label={`Disconnect ${name}`}
            >
              Disconnect
            </Button>
          </>
        ) : onConnect ? (
          <Button size="sm" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => onConnect(false)} disabled={busy} aria-label={`Connect ${name}`}>
            Connect
          </Button>
        ) : null}
      </div>
    </li>
  )
}

import { app } from 'electron'
import { existsSync } from 'fs'
import { delimiter, join } from 'path'
import { execFile } from 'child_process'
import { promisify } from 'util'

const execFileAsync = promisify(execFile)

/**
 * Resolve ffmpeg / ffprobe / yt-dlp. Prefer staged FFmpeg tools in development
 * and bundled tools in packaged builds. The clipping engine must use the same
 * FFmpeg that passes the caption filter check.
 */
export function resolveBinary(name: 'ffmpeg' | 'ffprobe' | 'yt-dlp'): string {
  const exe = process.platform === 'win32' ? `${name}.exe` : name
  if (!app.isPackaged && name === 'yt-dlp') {
    const venvTool = join(__dirname, '..', '..', 'engine', '.venv', process.platform === 'win32' ? 'Scripts' : 'bin', exe)
    if (existsSync(venvTool)) return venvTool
  }
  const binDir = app.isPackaged
    ? join(process.resourcesPath, 'engine-bin')
    : join(__dirname, '..', '..', 'engine-bin')
  const bundled = join(binDir, exe)
  // A damaged installation must fail, never execute a same-named PATH program.
  if (app.isPackaged || existsSync(bundled)) return bundled
  return name
}

/** Captioned BridgeClip renders require FFmpeg's libass-backed `ass` filter. */
export async function supportsCaptionFilter(): Promise<boolean> {
  try {
    const { stdout } = await execFileAsync(resolveBinary('ffmpeg'), ['-hide_banner', '-filters'], {
      timeout: 10000,
      maxBuffer: 1024 * 1024
    })
    return stdout.split('\n').some((line) => /^\s*[A-Z.]{2,}\s+ass\s/.test(line))
  } catch {
    return false
  }
}

/**
 * Mirror of `is_safe_opencode_command` (settings-store / bridge_runner):
 * a simple executable name or an absolute path, never shell metacharacters.
 */
function isSafeOpencodeCommand(value: string): boolean {
  if (typeof value !== 'string' || !value || value.length > 512) return false
  if (value.includes(String.fromCharCode(0))) return false
  if (value.includes('\r') || value.includes('\n') || value.includes('\t')) return false
  if (/[;&|$`'"<>() ]/.test(value)) return false
  if (value.includes('/') || value.includes('\\')) {
    const base = value.replace(/[/\\]+/g, '/').split('/').pop() ?? ''
    return base.length > 0 && /^[A-Za-z0-9_.-]+$/.test(base)
  }
  return /^[A-Za-z0-9_.-]+$/.test(value)
}

/**
 * Resolve an OpenCode CLI command to an executable path without a shell.
 * Absolute paths must exist; bare names are searched on PATH (PATHEXT on
 * Windows, where the CLI ships as `opencode.cmd`). Returns null when the
 * command is unsafe or not found. Never uses `shell: true`.
 */
export function resolveOpencodeCommand(command: string): string | null {
  if (!isSafeOpencodeCommand(command)) return null
  if (command.includes('/') || command.includes('\\')) {
    return existsSync(command) ? command : null
  }
  const pathValue = process.env.PATH || process.env.Path || ''
  const dirs = pathValue.split(delimiter).filter(Boolean)
  const extensions =
    process.platform === 'win32'
      ? (process.env.PATHEXT || '.COM;.EXE;.BAT;.CMD').split(';').filter(Boolean)
      : ['']
  for (const dir of dirs) {
    for (const ext of extensions) {
      const candidate = join(dir, `${command}${process.platform === 'win32' && ext === '' ? '' : ext}`)
      try {
        if (existsSync(candidate)) return candidate
      } catch { /* Keep searching PATH. */ }
    }
    // Bare executable without extension (POSIX, or win32 with explicit ext in PATHEXT miss).
    if (process.platform !== 'win32') {
      const candidate = join(dir, command)
      try {
        if (existsSync(candidate)) return candidate
      } catch { /* Keep searching PATH. */ }
    }
  }
  return null
}

/** OpenCode CLI is available when its (safe) command resolves on this machine. No service is invoked. */
export function isOpencodeAvailable(command: string): boolean {
  return resolveOpencodeCommand(command) !== null
}

/**
 * Check a Python module is importable with the resolved interpreter.
 * Used for `faster_whisper` and `yt_dlp`: import only, never downloads a
 * model or contacts a service.
 */
export async function checkPythonModule(pythonPath: string, enginePath: string, module: string): Promise<boolean> {
  try {
    const { execFile: rawExecFile } = await import('child_process')
    const { promisify: rawPromisify } = await import('util')
    const run = rawPromisify(rawExecFile)
    await run(pythonPath, ['-c', `import ${module}`], {
      cwd: enginePath,
      timeout: 15000
    })
    return true
  } catch {
    return false
  }
}

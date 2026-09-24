<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="resources/bridgeclip-logo.svg" />
    <img src="resources/bridgeclip-logo-light.svg" alt="BridgeClip" height="56" />
  </picture>
</p>

<h3 align="center">Turn long videos into captioned short-form clips, on your own computer.</h3>

<p align="center">
  An open-source AI clipping app from <a href="https://www.bridgemind.ai">BridgeMind</a>.
  Drop in a podcast, stream, YouTube link or Twitch VOD link, and BridgeClip finds the strongest moments,
  cuts them to 9:16 or 16:9, and burns in word-by-word captions.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License" /></a>
  <a href="https://github.com/bridge-mind/bridgeclip/releases"><img src="https://img.shields.io/github/v/release/bridge-mind/bridgeclip?label=download" alt="Latest release" /></a>
  <a href="https://www.bridgemind.ai/discord"><img src="https://img.shields.io/badge/Discord-builders-5865F2?logo=discord&logoColor=white" alt="Discord" /></a>
</p>

---

## Why BridgeClip?

- **No BridgeMind account or backend.** BridgeClip runs on your machine and calls your configured providers directly with your own keys and logins. By default that is local faster-whisper transcription plus the OpenCode CLI planner; OpenRouter is optional for its economy/quality transcription and planning paths. Optional social account connections use your Zernio account and API key. Your videos and keys do not pass through a BridgeMind server.
- **Pay only for what you use.** The default local faster-whisper transcription runs on your computer; the default OpenCode planner runs through your OpenCode login and its configured model, which may bill or log through that service. OpenRouter transcription and clip planning bill your OpenRouter account at their prices when you select them. Rendering happens locally with FFmpeg. BridgeClip shows estimated API cost when the providers return usable usage data.
- **Captions that look native.** Nine styles (Viral, Hormozi, Bold, Clean, Minimal, Fire, Glow, Neon, Karaoke), each with a live preview before you render.
- **MIT licensed.** Fork it, change it, ship it.

## How it works

```
 Source video ──▶ Download ──▶ Transcribe ──▶ Find moments ──▶ Render
 (file or link)    yt-dlp      local faster-    OpenCode CLI     FFmpeg
                               whisper          planner ranks    crop, captions,
                               (default)        the best         one file per clip
                                                moments
                           OpenRouter alternative: MAI Transcribe 2 / Whisper
                           Turbo transcription and LLM moment ranking,
                           with economy (z-ai/glm-5.3-flash, no vision) and
                           quality paths.
```

Every run gets its own folder. The **Library** shows completed clips with virality scores, timecodes and tags. **Jobs** shows what is running or queued right now (up to two clipping runs go at once; more wait in a queue) and every earlier run, including completed, failed, cancelled and interrupted jobs; completed runs open their clips, and failed runs from this session can run again. Older runs without a saved status appear as unfinished. You can optionally connect social accounts through Zernio to publish or schedule a selected clip.

## Download

Signed macOS builds for Apple silicon and Intel will appear on [Releases](https://github.com/bridge-mind/bridgeclip/releases) after release testing. Those builds bundle Python, FFmpeg and yt-dlp. Until then, use the development setup below. Windows runs only from a terminal via `npm run dev` from source; there is no installer or exe requirement and none is provided here. Windows source builds are experimental and are not part of the supported release workflow.

On first launch, the default local path needs no OpenRouter key: sign in the OpenCode CLI with an available model and make sure local transcription is ready in **Settings → System check**. Add an OpenRouter key in the setup card only if you select OpenRouter transcription/planning or enable the optional AI vision check:

| Provider | Used for | Get a key |
| --- | --- | --- |
| OpenRouter | MAI Transcribe 2 transcription and choosing the moments to clip | [openrouter.ai](https://openrouter.ai/keys) |

Keys are encrypted with your operating system's secure storage. If secure storage is unavailable, BridgeClip asks you to configure or unlock it before saving keys.

### What leaves your computer

For a link, the app downloads the source using your network connection. Default local transcription with faster-whisper runs on your computer and does not send audio to OpenRouter. The default OpenCode planner runs locally through the OpenCode CLI, but it may send transcript text to its configured service; check that service's data policy. Local transcription does not mean transcript text stays on this PC. If you instead select OpenRouter providers: audio for MAI Transcribe 2 (Quality) or Whisper Turbo (Economy) transcription goes to OpenRouter. Transcription retries temporary failures and uses fallback models when needed; Economy tries Whisper Large V3 before MAI and uses z-ai/glm-5.3-flash planning with no vision fallback. Transcript text for OpenRouter clip planning also goes to OpenRouter. On the OpenRouter path, if the video has no audio or no speech, BridgeClip samples video frames and sends those images to OpenRouter for visual-only planning; clips made through that fallback have no speech captions. The default local OpenCode planner has no vision model and needs a transcript, so speechless videos fail there instead. Economy skips optional AI layout checks. The optional AI vision check improves ambiguous layouts and can add OpenRouter cost. If you connect social accounts, BridgeClip sends your Zernio API key to Zernio and receives account/profile metadata; platform sign-in occurs in your browser. When you choose **Post** or **Schedule**, BridgeClip uploads that clip to Zernio's media storage and sends its caption, selected accounts and publishing options to Zernio. Zernio then publishes to those platforms. Provider accounts, charges, retention and data policies are governed by those services.

Downloads and intermediate media are held in a private `work/` directory under BridgeClip’s per-user application data folder. BridgeClip removes job work on completion, failure, and cancellation, and clears stale work when it next starts after a forced shutdown. A local video you selected stays where it was. Rendered clips, the transcript, plan and `job_output.json` remain in a run folder under your chosen **Output folder** (by default, `~/BridgeClip`). That JSON includes the source URL or local path and video title. Delete the run folder to remove those local outputs.

Settings, the last synced list of connected accounts (platforms, handles and Zernio IDs), local posting history, and upload retry records live in Electron's per-user application data folder. Posting history can include clip paths and titles, account handles, targets, status and links; retry records can include a clip path and an uploaded media URL. Changing or removing the Zernio key switches to a separate local post history and quarantines the old account and upload retry caches. Returning to the same key restores its saved post history; a newly rotated key has separate history. Quarantined copies remain on disk until a later cleanup after 30 days; to erase them immediately, quit the app and delete the `zernio-*.quarantine-*` files from its application data folder. Key changes do not delete media or posts already held by Zernio or a social platform. Diagnostic logs live in the per-user logs folder. Remove provider keys in Settings to clear their encrypted saved copies, and review logs before sharing them in an issue.

Only download or clip material you have permission to use. Remote sites may limit downloads or change their access rules.

### Clip a Twitch VOD

Paste a public, completed Twitch video link such as `https://www.twitch.tv/videos/1234567890` into Create, then choose your clip settings and generate. BridgeClip downloads the saved video and uses the same transcription, AI moment selection and rendering flow as other sources. Links on `twitch.tv`, `www.twitch.tv`, `m.twitch.tv` and `go.twitch.tv` are accepted and normalized to the canonical video URL.

Live channels, Twitch clips, collections, subscriber-only videos and deleted or expired VODs are not supported. No Twitch login or cookies are used. The original source must be at most six hours and 20 GB. BridgeClip downloads the full source before applying the optional start and end times; a link's timestamp or tracking parameters are ignored. For a longer source, trim a downloaded file before adding it. Downloads also stop after four hours or when less than 1 GB of free space would remain.

## Develop

**Prerequisites:** Node.js 22, Python 3.12, and FFmpeg with the libass-backed `ass` filter for captions. The clipping engine, model, fonts, and locked Python dependencies are included in this repository. In development, BridgeClip uses FFmpeg from `engine-bin/` when it exists, then falls back to your `PATH`. An OpenRouter key is only needed for live jobs that select OpenRouter providers or vision, not for the default local faster-whisper + OpenCode path and not for tests.

```bash
git clone https://github.com/bridge-mind/bridgeclip
cd bridgeclip
python3.12 -m venv engine/.venv
engine/.venv/bin/pip install --require-hashes -r engine/requirements.lock
npm ci
npm run dev
```

### Windows 10/11 (run from source)

Windows source builds are experimental; run them only from a terminal via `npm run dev`. There is no installer or exe to download and none is required. Windows distributable packaging (NSIS) is not verified, and resource staging is currently macOS-only.

**Prerequisites (x64):** Python 3.12, FFmpeg and FFprobe with the libass-backed `ass` filter (for example a full build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) or [BtbN](https://github.com/BtbN/FFmpeg-Builds)) on `PATH`, Node.js 22, and the [OpenCode CLI](https://opencode.ai/) signed in with an available model for the default local planner.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1
# or: npm run setup:windows
```

The script creates or reuses `engine\.venv` (an existing venv must report Python 3.12.x), installs `engine/requirements.lock` with `pip --require-hashes`, runs `npm ci` from the Node lockfile, verifies the `ass` filter via `ffmpeg -filters`, and then prints the next steps. It never stores API keys. End result after `npm run dev`:

- Dev Python path: `engine\.venv\Scripts\python.exe` (also detected automatically; check **Settings → System check**).
- Faster-Whisper downloads its model weights on first local transcription; nothing is pre-downloaded by setup.
- OpenCode must be logged in with an available model. OpenRouter planning and transcription remain available in Settings.
- Local transcription does not mean transcript text stays on this PC: the default OpenCode planner may send that text to its configured service.
- Finished clips are vertical MP4 files, same as other BridgeClip builds.

BridgeClip finds its in-repo engine and virtual environment automatically. **Settings → System check** shows the Python, yt-dlp, FFmpeg, and engine checks; set **Python path** in development if you use another interpreter.

On Linux, use system FFmpeg with the libass-backed `ass` filter (`ffmpeg -hide_banner -filters | grep -E '[[:space:]]ass[[:space:]]'`) and Python 3.12. Arch: `sudo pacman -S ffmpeg`. Skip `scripts/prepare-resources.sh` during development; it prepares macOS release resources. Linux development and tests are supported, but a self-contained Linux package is not yet available.

The release workflow packages the in-repo engine and media tools into signed macOS builds. For local packaging, first run `bash scripts/prepare-resources.sh arm64` (or `x64` on Intel), then follow [the release guide](docs/RELEASING.md). Signing credentials are still required for a distributable build.

### First run and troubleshooting

1. Sign in the OpenCode CLI with an available model for the default local planner; no OpenRouter key is needed for that path. If you select OpenRouter transcription/planning or enable vision, add your OpenRouter key in the setup card instead. A saved key is never shown again; paste a new one to replace it or choose **Remove key** in Settings.
2. Run **Settings → System check**. It verifies local faster-whisper, the OpenCode CLI, Python, yt-dlp, FFmpeg, and the engine. In development, set the Python path if your local virtual environment is not detected.
3. Choose a local video with the file picker or paste a public video link (YouTube or a public, completed Twitch VOD), select clip lengths, framing, caption style, and economy/quality, then start. Smart framing automatically follows faces and arranges screen shares with facecams shot by shot. The optional AI vision check improves ambiguous layouts and can add OpenRouter cost. Dropping a local file opens the picker so you can grant access. Completed runs appear in Library and in your output folder.
4. If a link fails, check it in a signed-out browser or download it yourself and select the local file. If a run fails, use the in-app error and System check first; logs intentionally omit raw provider responses and private source details.

| Script | What it does |
| --- | --- |
| `npm run dev` | Run the app with hot reload |
| `npm run typecheck` | Type-check the main process and renderer |
| `npm run lint` | Check TypeScript and JavaScript source with ESLint |
| `npm run build` | Production build into `out/` |
| `npm run test:bridge` | Run Python bridge regression tests |
| `engine/.venv/bin/python -m pytest -q engine/tests` | Run the clipping engine tests after installing pytest |
| `npm run test:release` | Check macOS updater metadata merging |
| `npm run test:renderer` | Check renderer state and parsing regressions |
| `npm run test:main` | Check desktop security and pipeline regressions |
| `npm run test:zernio` | Check social account, upload and posting flows against local mocks |
| `npm run dist:mac` | Package the current Mac architecture into `dist/` after preparing matching resources (signing needs a Developer ID) |
| `npm run icons` | Regenerate the app icon from `scripts/icon/` (macOS) |

### Project layout

```
src/main/        Electron main process: settings, pipeline runner, IPC, optional Zernio posting
src/preload/     The typed window.bridgeclip API exposed to the renderer
src/renderer/    React UI (Create, Library, Jobs, Accounts, Automations, Settings)
src/shared/      Product constants shared by main and renderer
bridge/          Python worker protocol and network guard
engine/          BridgeClip clipping engine, assets, locked Python dependencies, and tests
scripts/icon/    Icon and logo generators
```

The visual system (tokens, components and rules) is documented in [DESIGN.md](DESIGN.md).
The desktop trust boundaries and bridge protocol are described in [Architecture](docs/ARCHITECTURE.md).
The [open-source readiness checklist](docs/OPEN_SOURCE_READINESS.md) tracks the remaining release gates and maintenance priorities.

## Contributing

Issues and pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) for setup, review expectations and checks. Security reports should follow [SECURITY.md](SECURITY.md), not a public issue. The community guidelines are in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

[MIT](LICENSE) © BridgeMind

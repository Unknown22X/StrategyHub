# StrategyHub Submission Checklist

Use this as the final Build Week / Devpost checklist. Replace every `[ADD ...]` field before submission.

## Project basics

- [ ] Project name is **StrategyHub**.
- [ ] One-line description is clear and does not promise profits.
- [ ] Category selected from the actual Devpost options: `[ADD CATEGORY]`.
- [ ] Country entered: `Saudi Arabia — confirm before submitting`.
- [ ] Built With tags include:
  - [ ] GPT-5.6
  - [ ] Codex
  - [ ] Python
  - [ ] FastAPI
  - [ ] React
  - [ ] TypeScript
  - [ ] SQLAlchemy
  - [ ] Gate.io
  - [ ] Windows

## Devpost project story

- [ ] Explain that I built StrategyHub to help my dad understand and safely test trading Strategies.
- [ ] Explain the problem: trading bots often mix technical settings, readiness, risk, and runtime state in confusing ways.
- [ ] Explain the solution: one local app for Paper Orders, Strategy Instances, Opportunities, Backtesting, Risk Management, and authoritative environment separation.
- [ ] Clearly state that the goal is safer operation and understanding—not guaranteed returns.
- [ ] Distinguish pre-existing work from Build Week improvements using `BUILD_WEEK_CHANGES.md`.
- [ ] Mention the most important Build Week changes:
  - [ ] authoritative Paper/Testnet/Live lifecycle;
  - [ ] safe zero-Quantity Preview;
  - [ ] reconciliation and risk readiness;
  - [ ] daily baseline and limit toggles;
  - [ ] Template/Preset/Instance model;
  - [ ] direct Paper start and immutable Run snapshots;
  - [ ] Strategy lifecycle and operations page;
  - [ ] Opportunities redesign;
  - [ ] contract picker and live freshness;
  - [ ] reliable beginner Backtesting.
- [ ] Describe how GPT-5.6 was used for reasoning, UX, safety modeling, review, and documentation.
- [ ] Describe how Codex inspected, implemented, migrated, tested, and packaged the local repository.
- [ ] Include the safety statement: no Live Credentials, Live Orders, real transactions, or real funds were used.

## Links

- [ ] GitHub repository URL: `[ADD GITHUB URL]`.
- [ ] Repository is accessible to judges before submitting.
- [ ] Default branch points to the stable final commit.
- [ ] README renders correctly on GitHub.
- [ ] Try It Out link: `[ADD DOWNLOAD OR RELEASE URL]`.
- [ ] If the Try It Out link is a GitHub Release, attach `RangeBot-Setup.exe` and explain that the public project is StrategyHub while stable internals retain RangeBot.
- [ ] YouTube demo URL: `[ADD YOUTUBE URL]`.
- [ ] Video visibility allows judges to watch it without requesting access.

## Demo video

- [ ] Follow `DEMO.md`.
- [ ] Video is under three minutes.
- [ ] Story for my dad is said in the opening.
- [ ] PAPER badge is visible before the first Order action.
- [ ] No Credentials, API keys, secrets, or private account data appear.
- [ ] Paper Order Preview shows Quantity, Margin, Leverage, fees, Take Profit, and Stop Loss.
- [ ] Paper Position, PnL, protection, and close are shown.
- [ ] Direct Paper Strategy start without Backtest is shown.
- [ ] Running and stopped Strategy status are shown.
- [ ] Opportunities Review and Shortlist/Ignore behavior are shown.
- [ ] One prepared Backtest result is shown, or the limitation is stated honestly.
- [ ] Risk Management toggles and Emergency Stop are shown.
- [ ] Paper/Testnet/Live separation is mentioned without entering Live.
- [ ] GPT-5.6 and Codex are mentioned.
- [ ] No profit guarantee is made.

## Screenshots

- [ ] Dashboard with StrategyHub branding and PAPER badge.
- [ ] Paper BTC_USDT Order Preview.
- [ ] Paper Position with PnL and protection.
- [ ] Running Strategy Instance operations page.
- [ ] Opportunity Review and Strategy selector.
- [ ] Completed Backtest result.
- [ ] Risk Management toggles and Emergency Stop.
- [ ] Images contain no Credentials or private information.
- [ ] Add files under `docs/screenshots/` or upload them manually to Devpost.

## Codex evidence

- [ ] Obtain the Codex Session ID from `/feedback` or the `CODEX_THREAD_ID` environment variable.
- [ ] Codex Session ID: `[ADD CODEX SESSION ID]`.
- [ ] Save any required screenshot or transcript evidence allowed by the event rules.
- [ ] Do not expose unrelated private conversation content or secrets.

## Repository and release

- [ ] Stable final commit hash recorded: `[ADD FINAL COMMIT]`.
- [ ] Final Git working tree is clean.
- [ ] Secret scan passed.
- [ ] No `.env` containing secrets is committed.
- [ ] No local database, account snapshot, Credential file, private log, or backup is committed.
- [ ] `KNOWN_LIMITATIONS.md` is current.
- [ ] `BUILD_WEEK_CHANGES.md` matches the actual commit history.
- [ ] `USER_GUIDE.md` matches the final Paper-first behavior.
- [ ] Frontend tests pass.
- [ ] Frontend typecheck passes.
- [ ] Frontend production build passes.
- [ ] Focused Python release tests pass.
- [ ] Ruff check and format check pass.
- [ ] Database migration tests pass.
- [ ] Windows installer built successfully.
- [ ] Installer path recorded: `[ADD ABSOLUTE INSTALLER PATH]`.
- [ ] Application version recorded: `0.1.0` unless intentionally changed before final build.

## Installed Windows verification

- [ ] Install the final `RangeBot-Setup.exe` on Windows.
- [ ] Confirm `RangeBotEngine` starts.
- [ ] Confirm `http://127.0.0.1:8765/app/` opens.
- [ ] Confirm PAPER is the authoritative active environment.
- [ ] Confirm Paper works without Gate.io Credentials.
- [ ] Run the Paper demo path once in the installed build.
- [ ] Close and reopen the launcher.
- [ ] Confirm state and Emergency Stop persistence.
- [ ] Uninstall while choosing to preserve personal data.
- [ ] Confirm the service is removed and the preserved data folder is not damaged.
- [ ] Reinstall if needed for the final recording.

## Known limitations and honesty

- [ ] State that real Gate.io Testnet acceptance was not completed unless I personally complete it.
- [ ] State that no Live testing was performed.
- [ ] State that public market data needs internet access and can be stale/unavailable.
- [ ] State that the Windows/internal name remains RangeBot for release stability.
- [ ] State that some advanced screens retain mixed Arabic explanations and English trading terms.
- [ ] State that Paper and Backtest results do not guarantee Live performance.

## Manual files to upload

- [ ] Final installer: `RangeBot-Setup.exe`.
- [ ] Demo video or YouTube URL.
- [ ] Final screenshots.
- [ ] Any required project thumbnail or banner.
- [ ] GitHub repository link.
- [ ] Try It Out / Release link.
- [ ] Codex Session ID.

## Final submission timing

- [ ] Submit an initial complete version early rather than waiting for the last minute.
- [ ] Reopen the Devpost submission after saving and confirm every link works.
- [ ] Watch the uploaded video from a logged-out/private browser window.
- [ ] Download the installer from the public Try It Out link and verify its checksum/path.
- [ ] Make the final text edits before the deadline; do not begin new product features.

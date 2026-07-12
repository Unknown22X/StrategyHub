# Arabic RTL visual verification

The final native PySide6 interface was rendered offscreen at 1440×900 and reviewed
against the supplied HTML reference and screenshot. The implementation copies no HTML;
it uses standard Qt layouts and controls throughout.

Verified visually:

- calm charcoal/teal palette, restrained amber warnings, and a fixed right sidebar;
- one obvious first-use CTA: **اختر عملة للبدء**;
- compact status metrics without oversized empty cards;
- a prominent trade panel containing amount, leverage, TP/SL, Market/Limit, and separate
  green Long and red Short actions;
- monitoring and automatic trading presented separately;
- watchlist, position/protection, recent activity, safety state, and emergency action
  visible from the dashboard;
- correct Arabic-first hierarchy with isolated LTR contract, number, and English-token
  content;
- no JSON, raw HTTP URL, stack trace, or technical transport error in the user surface.

Typography uses the bundled Thmanyah Sans Regular, Medium, and Bold files through
`QFontDatabase.addApplicationFont`, with Segoe UI as the safe fallback. The three font
files are also included in the PyInstaller UI bundle.

Visual evidence: `artifacts/ui-dashboard-ar.png`.

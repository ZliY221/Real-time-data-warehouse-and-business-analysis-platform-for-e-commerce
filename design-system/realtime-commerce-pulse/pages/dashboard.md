# Dashboard Page Overrides

These decisions override the generated master design system for the production dashboard.

- Use the local system font stack with Fira Sans/Fira Code as optional first choices. Do not load remote fonts, so the dashboard avoids font blocking and keeps a narrow Content Security Policy.
- Do not add GSAP. ECharts data transitions and 150–260 ms CSS state transitions provide enough motion for an operational dashboard.
- KPI cards are informational, not clickable; therefore they do not use pointer cursors or layout-shifting hover transforms.
- Keep all interactive controls at least 44 px high, with visible keyboard focus and semantic HTML controls.
- Use a line-plus-bar chart for the time series, a horizontal bar chart for regions, and a donut chart with decal support for channels. Tables remain available as the non-visual fallback.
- Preview data must always display an explicit warning and a distinct non-live connection state.
- Support light and dark color schemes through semantic tokens and respect `prefers-reduced-motion`.

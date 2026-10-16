# Accessibility

Target: WCAG 2.2 level AA. Last checked 2026-10-16.

## What is verified automatically

All of these run in `npm run test:e2e` (Chrome) or `npm test`.

| Area | Check |
|---|---|
| Automated rules | axe-core with WCAG 2 A/AA, 2.1 A/AA, 2.2 AA and best-practice tags: no violations on the compare page (empty, filled, drop state), the results page (with an expanded source line and an answer), the benchmark page and the 404 page, in light and dark, and with a manual theme that differs from the system theme |
| Structure | one banner, one main, a named navigation, one h1 per page, no skipped heading level, `lang="en"`, a distinct page title on every screen (the results page names both versions) |
| Names and state | filters expose `aria-pressed`, the selected change exposes `aria-current`, hop lists and tables have names and captions, every control has an accessible name |
| Keyboard | every tab stop on the results page is visible, shows a focus indicator and follows page order; Shift+Tab walks back out; Enter and Space operate every control; choosing a change moves focus to its heading; skip link works |
| Announcements | the file status lines, the submit hint, the answer area and the source panel are live regions that exist before their text changes; adding and removing files is announced in words |
| Forced colors | with `forced-colors: active` the pressed filter, selected change, cited line and classification marks still show |
| Preferences | reduced motion removes transitions; browser text at 200% and 300% does not scroll sideways; the WCAG 1.4.12 text-spacing override clips and overflows nothing |
| Reflow and targets | no sideways scroll at 320 px and 375 px; every button and navigation link is at least 44 px high |
| Color | every text pair was computed with the WCAG 2 contrast formula (see `DESIGN.md`); control borders are at least 3:1; confirmed versus inferred and each classification are distinguished by word and shape, never color alone |
| Alternative to dragging | drag and drop is an extra; "Add files" and "Add folder" do the same with a single click (WCAG 2.5.7) |

## What is not verified

- **No real screen reader was run.** axe and the checks above catch missing names, roles, states and live regions, but not how NVDA, JAWS, VoiceOver or TalkBack read the page, in what order, or how verbose they are. A person with one of them should go through the list below.
- No test with voice control, switch access or a screen magnifier.
- No review by people with disabilities.
- Safari and Firefox were not run; the tests use Chrome.

## Manual pass to do with a screen reader

1. Open `/`. Move through the page by headings, by landmarks and by form fields. Check that the two version boxes read as "Version A (before)" and "Version B (after)" groups.
2. Press "Load petstore example". Check that the status line announces what was added and the hint changes to "Ready to compare."
3. Press "Compare versions". Check that the new page announces its title ("v1 to v2 | SpecTrace") and that the heading and summary read sensibly.
4. In the change list, choose a change. Check that focus lands on its heading and the heading is announced.
5. Read one impact. Check that the hop list is announced as a numbered list that names the impacted entity and the change, and that "Confirmed" and "Inferred 80%" are spoken.
6. Press "Show source at ...". Check that the source lines are announced, and that the cited line is identifiable (its number is read first).
7. Ask a question. Check that the answer heading and reason are announced without moving focus.
8. Check the theme buttons are announced as a group "Color theme" with their pressed state.
9. Drop a file onto a version box with a pointer and check the status line announces it.

Record any problem as an issue with the reader and browser used.

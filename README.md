# PR Link Report Builder

**English** · [中文](README.zh.md)

> **Live demo:** <https://treeaspen.github.io/pr-link-report/> — the hosted build ships with the logo library and the full sample report.
> **Tutorial:** <https://treeaspen.github.io/pr-link-report/tutorial.html> — bilingual walkthrough, also available offline as `tutorial.html`.

Turn a spreadsheet — or just a list of URLs — into a press-release distribution report
with clickable hyperlinks, outlet logos and page screenshots.
Single file, runs in the browser, no server and no network required.

It can **extract outlet logos from a distribution-report PDF and map them to link domains**,
so afterwards you paste a reprint URL and the outlet name, location and logo fill themselves in.

<sub>Interface available in English and 简体中文 — toggle in the top-right of the sidebar.</sub>

---

## Quick start

```bash
git clone https://github.com/TreeAspen/pr-link-report.git
cd pr-link-report
```

Open `index.html` in your browser — that is the whole tool. For automatic logo matching
and the full sample report, one more step:

```bash
pip install -r requirements.txt

# put your distribution-report PDF in this folder, then:
python extract_logos.py      # build the logo library  → logos.js
python build_sample.py       # rebuild the full sample → sample.js
```

Reload `index.html`; the sidebar will show `Logo library: N outlets / M logos`.

---

## What it does

### Bulk import

- Paste straight from Excel / Google Sheets with `Ctrl+V`; columns are detected automatically
- Reads **hyperlinks carried by the cells themselves** — no separate URL column needed
- A *group* column splits one paste into several sections at once
- Pasting a bare list of URLs works too — everything else comes from the logo library

### Logo library

`extract_logos.py` walks the PDF's link annotations, locates each outlet card by
coordinates, and pairs the logo inside it with the outlet name, location and target domain.

Bitmap, inline and **vector** logos are all handled through one path: the logo region is
rasterised from the page, white margins trimmed, encoding chosen for the smaller file.
Blank regions are detected and skipped. Run several reports through it and the library
merges and de-duplicates, growing over time.

Matching order: exact domain → strip sub-domains one level at a time → registrable domain →
outlet name. `www.` / `m.` / `amp.` prefixes are ignored.

### Layouts

| Type | Notes |
|---|---|
| Brand tiles, 2–4 columns | Logo when available, otherwise the outlet name |
| Cards, 1–4 columns | Name + location, small logo on the right |
| Screenshots, 1–3 columns | Whole image is the link |
| Link list, 3 columns | Row-major order, matching the source report |
| Pills / table | — |
| World media directory | Region + target count + three-column outlet list |
| Social share row | Facebook / X / LinkedIn / Bluesky |
| Report summary panel | Word counts, anchor-text links, embedded images and captions |

### Screenshots

- Drag an image onto any card (drop several to fill consecutive entries)
- Click a card, then `Ctrl+V` to paste from the clipboard
- Select many files at once — **matched to entries by filename**
  (exact → fuzzy → `01_` numeric prefix → fill remaining slots in order)

Screenshots live in IndexedDB (localStorage cannot hold them) and are resized to 1400px wide
on import.

### In-place editing

Titles, names and locations in the preview are directly editable. On editable text a plain click edits and
`Ctrl+click` follows the link; non-editable links (tile logos, screenshots, the directory, share buttons,
summary links) open in a new tab on a plain click.

### Theming

Eight colour presets (navy is the default) restyle the whole report in one click, with
free-form colour pickers underneath for anything else.

---

## Export

| Route | Hyperlinks | Images |
|---|---|---|
| Print / Save as PDF | ✅ including in-document TOC anchors | ✅ |
| Copy to Google Docs | ✅ | usually ✅ |
| Download `.doc` | ✅ | usually ✅ |
| Download `.html` | ✅ | ✅ |
| Import PDF into Canva | ❌ Canva strips links | ✅ |

Google Docs ignores CSS grid and flex, so the clipboard copy uses a separate
**table plus inline-style** serialisation — the layout survives the paste.

For Canva: tick *Appendix: link index*, use *Export all screenshots as files* to get the
originals (numbered in report order), then re-attach links in Canva from that list.

---

## Files

```
index.html            the tool (single file, all CSS/JS inline)
tutorial.html         bilingual tutorial page (standalone)
extract_logos.py      PDF → logo library
build_sample.py       PDF → full sample project
logos.js              generated: the library, with PNGs inlined
logos_manifest.json   generated: name/domain table — correct it by hand and re-run
logos/                generated: individual PNG files
sample.js             generated: the sample project
```

`logos.js` and `sample.js` are committed so the hosted demo works out of the box; `logos/`
and `logos_manifest.json` are intermediates and are ignored (every image is already inlined in
`logos.js`). Re-run the two scripts on your own reports to replace them. If either file is
missing, the tool falls back to a small built-in sample and nothing else changes.

## Requirements

Browser: Chrome or Edge (uses IndexedDB, `ClipboardItem`, CSS multi-column).
Scripts: Python 3.9+ with `pymupdf` and `pillow`.

## License

MIT

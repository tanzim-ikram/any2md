# Any2MD

Any2MD is a fast, beautiful, local-first Windows desktop application for converting common document formats to and from Markdown.

All conversions run 100% locally on your machine — your files never leave your computer.

---

## Features
    
- **Document to Markdown**: Convert PDF, Word (.docx), Excel (.xlsx, .xls), PowerPoint (.pptx, .ppt), Plain Text (.txt), HTML (.html), and CSV (.csv) directly into clean Markdown powered by Microsoft MarkItDown.
- **Markdown to Document**: Convert Markdown files (.md) into styled PDF (via WeasyPrint), formatted Word (.docx), or HTML.
- **Direct Document-to-Document Conversion**: Automatically converts non-Markdown documents directly to Word (.docx), HTML, or PDF using an automated two-hop pipeline.
- **Batch Processing**: Drag and drop multiple files to convert them simultaneously with real-time per-file progress tracking.
- **Theme Support**: Seamless Dark, Light, and System themes with Windows registry detection.
- **Recent History**: Quick access to recently converted files with double-click to open and reveal-in-folder actions.
- **Private & Offline**: No cloud dependencies or external network requests.

---

## Installation & Running

### Requirements
- Python 3.10+
- Windows 10 or 11

### Setup
```bash
pip install -r requirements.txt
```

### Run
```bash
python -m any2md.main
```
Or double-click `run.bat`.

---

## Keyboard Shortcuts
- `Ctrl+O` — Open file dialog to choose documents
- `Ctrl+,` — Toggle Settings panel
- `Esc` — Close settings / cancel conversion / return to drop zone

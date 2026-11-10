# Front-end Design Specification: Research Assistant UI.

A comprehensive architecture and design specification document based on the three-column AI Research Assistant interface.

## 1. Overview & Architecture

The application adopts a **3-column split-panel productivity layout** optimized for high-information density, PDF document analysis, and generative answers for Questions :

1. **Left Panel (`Source`):** Input data ingestion ( PDF files).

2. **Center Panel (`Canvas & Chat`):** Context exploration, quick-prompt chips, and chat input. Also acts as the view-port for source preview and source selection modals.

3. **Right Panel (`Summary`):** .

## 2. Layout Structure & Grid

```
+---------------------------------------------------------------------------------------+
| Top Navigation Bar (Logo, Document Title)           Action Buttons: Print,Theme Toggle|
+-------------------+-----------------------------------------------+-------------------+
|                   |                                               |                   |
|                   |                                               |   Summary Panel   |
|   Source  Panel   |               - Welcome                       |                   |
|   - Add Source    |               - Quick Prompts                 |                   |
|                   |                                               |                   |
|                   |                                               |                   |
|                   |-----------------------------------------------|                   |
|                   | Chat Text Input                       (Send)  |                   |
|                   |                                               |                   |
+-------------------+-----------------------------------------------+-------------------+

```

### Grid Dimensions & Breakpoints

* **Left Panel (`Sources`):** `w-72` to `w-80` (approx. 280px–320px), collapsable.

* **Center Panel (`Main`):** `flex-1 min-w-0`, dynamic fluid width.

* **Right Panel (`Studio`):** `w-80` to `w-96` (approx. 320px–384px), collapsable.

* **Breakpoints:**

  * `< 1024px`: Right panel converts to an overlay drawer.

  * `< 768px`: Left panel collapses into a sliding hamburger drawer; single-column mobile view with bottom navigation tabs (`Source`, `Chat`, `Summary`).

## 3. Design System & Tokens

### 3.1 Color Palette

Default theme: light.

* Light and dark both themes

| Token Name | Hex Code / Tailwind Equivalent | Role | 
| ----- | ----- | ----- | 
| `--bg-base` | `#0f1012` (`bg-[#0e0f12]`) | Root background | 
| `--surface-panel` | `#16171a` (`bg-[#16171a]`) | Card & sidebar surface | 
| `--surface-elevated` | `#212328` (`bg-[#202227]`) | Modal dialogs, popovers, dropdowns | 
| `--surface-pill` | `#2a2c33` (`bg-[#282a30]`) | Interactive pills, buttons, tags | 
| `--surface-pill-hover` | `#353842` | Hover state for pills | 
| `--border-subtle` | `#2d3139` (`border-[#2b2f38]`) | Dividers and thin outlines | 
| `--text-primary` | `#f1f3f5` (`text-gray-100`) | Headings, active values | 
| `--text-secondary` | `#9aa0a6` (`text-gray-400`) | Secondary descriptions, placeholders | 
| `--text-muted` | `#6b7280` (`text-gray-500`) | Footnotes, inactive indicators | 
| `--accent-blue` | `#8ab4f8` (`text-[#8ab4f8]`) | Interactive links, active tab highlights | 
| `--accent-gradient` | `linear-gradient(135deg, #a78bfa, #ec4899, #f59e0b)` | Feature banner accents | 

### 3.2 Typography

* **Font Family:** Inter, Google Sans, or Roboto (`font-sans`)

* **Scale:**

  * Title/Heading 1: `text-2xl` to `text-3xl` (`font-normal` or `font-semibold`)

  * Section Headers: `text-base font-medium text-gray-200`

  * Body & Interactive Pills: `text-sm font-normal text-gray-300`

  * Captions & Badges: `text-xs text-gray-400`

### 3.3 Radii & Elevation

* **Panels:** `rounded-2xl` (16px) or `rounded-3xl` (24px) for inner containers.

* **Interactive Pills & Inputs:** `rounded-full` (9999px) for search bars and action chips; `rounded-xl` (12px) for modal and studio cards.

* **Modals:** `rounded-2xl` with backdrop blur (`backdrop-blur-md bg-black/60`).

## 4. Component Breakdown & Specifications

### 4.1 Top Navigation Bar

* **Left:** Brand Icon + Document Title (`<input class="bg-transparent font-medium" />` with inline rename capability).

* **Right:**

  * `Print` button. placed to the left of the theme toggle.

  * `Theme Switch Toggle` button.

### 4.2 Source Panel (Left Column)

* **Header:** Title "Sources" with a collapse icon (`PanelLeftClose`).

* **Upload Control:**
  * A single drop zone is the only upload control. It accepts a click, a drag and drop, or Enter/Space when focused.
  * Its label is “Click to upload or drag and drop”, with the caption “PDF documents only (up to 20MB)”.
  * After a paper is uploaded, the drop zone becomes a compact row showing the filename and an “Upload another paper” link.
  * The “+ Add PDF Document” button is removed from the Source panel.

* **Below the upload zone (shown only before a paper is uploaded):**
  * A secondary button labelled “Convert other files”.
  * A caption under it: “Opens iLovePDF in a new tab. Your file is sent to iLovePDF, not to Research Assistant.”
  * The button opens https://www.ilovepdf.com with target="_blank" and rel="noopener noreferrer".

### 4.3 Center Workspace & Chat (Center Column)

* **Hero Section (Empty State):**

  * Emoji HI.

  * Dynamic header: `"Let's start your Research..."`

* **Bottom Query Bar:**

  * Floating bar anchored to bottom center.

  * Pill design with Sparkle icon on left, Source counter (`0 source`), and Send button ( inside circle)

  * System disclaimer: *"Strictly Depend on Uploaded PDF"*

### 4.4 Summary Panel (Right Column)

* Title & Authors and Abstract

* Problem Statement

* Methodology

* Key Results

* Conclusion

### 4.5 "Add Source" Modal Dialog

* **Center Overlay Card:**

  * Title: `"Upload your Research Paper"` (dynamic suggestion).

  * Source Categories (Grid of pill buttons):

    * `Upload PDF file`

  * Drag & Drop file dropzone with supported format indicators (`PDF only`).

### 4.6 Document Credibility & Reporting Signals Card (Left Column)

* **Layout Placement:** Located in the **Left Sidebar ("Sources" panel), positioned directly below the uploaded document item** (above "Convert other files"). The right sidebar remains dedicated exclusively to the five-part Summary.
* **Primary Display:** A clean 5-row visual signal checklist (Venue/Host, Citations, References, Affiliations, Structure) with clear status badges based on OpenAlex indexing and reporting scores:
  * **Score >= 75:** `"Indexed in OpenAlex"` (Green badge)
  * **Score 55–74:** `"Preprint Series"` (Yellow badge)
  * **Score < 55:** `"Unindexed Draft"` (Neutral badge)
* **Detail State Transitions:**
  * **Empty state (no document uploaded):** Card is hidden.
  * **Processing state:** Skeleton / spinner with *"Analyzing publication signals..."*.
  * **Completed state:** 5-row signal checklist with badge and secondary score figure.
  * **Timeout (> 30s) / Error state:** *"Analysis unavailable"*.
* **Reporting Disclaimer:** Subtext clearly visible on the card: *"This score reflects structural reporting signals and database matches, not scientific validity."*
* **Estimated References Tooltip:** If estimated references count is under 20, render an *"Estimated from layout"* tooltip.
* **Author Affiliation Shape:** Awarded when verified via OpenAlex institutional affiliations or when author contact lines match academic domain patterns (`.edu`, `.edu.<country_code>`, `.ac`, `.ac.<country_code>`, `.gov`, `.gov.<country_code>`). Verifies domain pattern shape and global registry metadata, not institutional authentication.

## 4.7 Export

The top bar button is labelled “Export”. Its tooltip reads “Downloads an editable Word file.”
Disabled, with the reason “Upload a paper first.”, when there is no summary.
Clicking shows a short “Preparing file” state, then starts the download.
Errors show the server message, as text.
The print styles are removed.

## 5. How You Can Customize This Frontend

You can customize this layout in several ways depending on your use case:

### 1. Theme & Color Palette

* **Light Mode:** Invert backgrounds to `bg-gray-50` / `bg-white`, change pill colors to `bg-gray-100`, borders to `border-gray-200`, and typography to `text-gray-900`.

* **Brand Accents:** Swap the default blue (`#8ab4f8`) with your own brand color (emerald, indigo, purple, rose).

### 2. Layout Flexibility

* **Collapsible Sidebars:** Add state (`isLeftOpen`, `isRightOpen`) so either sidebar can collapse into thin icon bars, giving the center canvas 100% focus.

* **Canvas Modes:** Replace the empty prompt state with a rich markdown editor, split source-viewer (PDF on left, chat on right), or whiteboard canvas.

### 3. Source Types

* In the Add Sources modal, customize the ingestion channels to fit your backend

## 4. Recommended Tech Stack

* **Framework:** Next.js (React 19) or Vite + React / SvelteKit

* **Styling:** Tailwind CSS v3 or v4 (using CSS variables for theme switching)

* **Icons:** Lucide React (`lucide-react`) or Phosphor Icons

* **State Management:** We use React state and hooks. The app has little shared state.

## 4.9 Authentication screens

### Sign-in and sign-up page

- Single centred card, `rounded-2xl`, on the page background, with the Mitra logo above it.
- Two tabs: **Sign in** and **Sign up**. Sign in is the default.
- Fields: email, password. Sign up adds a "Confirm password" field.
- Primary button full width: "Sign in" or "Create account".
- Link below the card switches between the two tabs.

### Errors

| Condition | Message |
|---|---|
| Wrong email or password | "Email or password is incorrect." |
| Email already registered | "An account with this email already exists." |
| Password under 8 characters | "Password must be at least 8 characters." |
| Passwords do not match | "Passwords do not match." |
| Too many attempts | "Too many attempts. Try again in a few minutes." |
| Session expired | "Your session has ended. Sign in again to continue." |

Errors appear inline above the button, with an icon and text. Colour is not the only signal.

### Signed-in state

- The top bar shows the user's email, truncated, and a **Sign out** button, placed to the left of the theme toggle.
- Signing out returns to the sign-in page and clears the workspace.

### Accessibility

- Tabs follow the ARIA tab pattern and respond to the arrow keys.
- Each field has a visible label, and error text is linked to its field with `aria-describedby`.
- The primary button shows a loading state and is disabled while the request runs.
- Focus moves to the first error when a submission fails.

### Behaviour

- While the session is being checked, the app shows the startup screen, not the sign-in page.
- A signed-in user who reloads the page stays signed in while the token is valid.

## 4.10 Profile menu

- An avatar with initials from the display name, or from the email if no name is set.
- The menu shows the name and email, then "Edit profile", "Change password", and "Sign out".
- Closes on Escape and outside click, returns focus to the avatar.

### 4.12 Help button and panel

- An icon button in the top bar labelled “Help”, immediately left of the theme toggle.
- A single responsive panel: a right-side drawer from the lg breakpoint (1024px) upward, and a bottom sheet below it. Use Tailwind classes only, with no viewport checks in JavaScript.
- Titled “How to use Mitra”.
- Seven ordered sections: Getting started, Reading the summary, Asking questions, Citations, Exporting, Account, Limits.
- Closes with Escape, the close button, or a backdrop click, and returns focus to the Help button.

### 4.13 PDF viewer

- **ViewPdfButton:** Sits in the top bar actions area, between the Export and Help controls. It appears only when a document is active, and is hidden after “Upload another paper”. Below lg, it shows as an icon only, with `aria-label="View PDF"` and a title tooltip.
- **PdfViewerDrawer:** A dialog with `role="dialog"`, `aria-modal="true"`, and `aria-label="Original PDF Document"`. Below lg it is a full-height modal. From lg upward it is a right-hand half-screen drawer (`lg:w-1/2`).
- **Embedding:** The PDF is embedded with `<object data={blobUrl} type="application/pdf">`.
- **Privacy statement:** Shown in the drawer header area as small text: “The PDF is shown from memory in your browser. The server keeps only the extracted text and index, as before.”
- **Fallback:** If inline rendering fails or the browser doesn’t support it, show “Your browser can’t show this PDF inline.” with an “Open in new tab” link.
- **Dismissal:** Escape, the close button, or a backdrop click. Focus returns to the View PDF button.

---

## 6. Mathematical Notation & Rendering Architecture

Research papers in computer science, physics, economics, and mathematics frequently present equations, loss functions, and Greek variable symbols. The frontend provides native LaTeX rendering across both structured summaries and conversational chat bubbles.

### 6.1 Package Architecture
- **Rendering Stack**: `react-markdown` (v10) with `remark-math` (v6), `rehype-katex` (v7), and `katex` (v0.19).
- **Global Stylesheet**: `katex/dist/katex.min.css` is imported once in `frontend/app/layout.tsx` to furnish all necessary font metrics, glyphs, and layout rules for KaTeX math markup.

### 6.2 Preprocessing & Delimiter Normalization
LLMs output mathematical notation in diverse formats, most commonly LaTeX inline delimiters `\( ... \)` and block delimiters `\[ ... \]`, alongside standard dollar notation (`$...$` and `$$...$$`).
- A dedicated utility function `preprocessLaTeX()` in `frontend/components/MarkdownRenderer.tsx` handles normalization before markdown parsing:
  1. **Code Block Isolation**: Splits incoming text on triple backticks (```) and inline code spans (`` ` ``) so that syntax within code snippets is preserved verbatim.
  2. **Display Block Normalization**: Transforms `\[...\]` (and `\\[...\\]`) into display math fences `\n\n$$\n...\n$$\n\n`, ensuring valid CommonMark flow block boundaries.
  3. **Inline Normalization**: Transforms `\(...\)` (and `\\(...\\)`) into trimmed inline dollar syntax `$ ... $`.
  4. **Display Math Overflow Handling**: Display math blocks (`.katex-display`) are styled with horizontal scrolling (`overflow-x: auto`) to prevent viewport breakage on narrow mobile screens or split-panel views.

---

## 7. Content Security Boundary & Untrusted Output Sanitization

A fundamental security principle of the application is that **all document text and LLM outputs are treated as untrusted content**.

### 7.1 XSS Elimination via Markdown AST
- **No Raw HTML Execution**: `rehype-raw` is strictly omitted from the markdown rendering pipeline.
- **Entity Escaping**: When untrusted inputs containing raw HTML tags (e.g., `<script>`, `<img onerror=...>`, `<iframe>`) are processed by `react-markdown`, they are parsed as literal text nodes and rendered as escaped entities (`&lt;script&gt;`).
- **CSS Sandboxing**: KaTeX HTML output generates isolated `<span class="katex">` and MathML `<math>` nodes without injecting unsafe inline executable scripts.

---

## 8. Universal Multilingual QA Policy & Prompt Contract

The Q&A service in `backend/app/services/qa.py` enforces a universal language policy governed by prompt contract invariants, eliminating fragile language keyword dictionaries or if-else language branches:

1. **Native Script Enforcement**: When a user queries in a non-English language (e.g., Sinhala, Tamil, Japanese, Spanish), the model replies in that language using its official native script (e.g., Sinhala Unicode script `සිංහල අකුරු`).
2. **Phonetic Slang Suppression**: If a user submits a question using romanised or transliterated slang (e.g., phonetic Singlish or Hinglish), the model identifies the underlying language and replies strictly in native script, never in Latin/romanised characters.
3. **English Academic & Technical Term Preservation**: Specialised technical terms, architectural components, variable names, framework acronyms, and named entities (e.g., *Transformer architecture*, *Multi-Head Attention*, *BLEU score*, *Adam optimizer*) are kept in standard English form to avoid awkward transliterations and preserve precision.
4. **Immutable English Fallback Contract**: When retrieved excerpts contain zero supporting evidence for a question, the model returns strictly the exact English fallback string:
   `"The uploaded paper does not contain information to answer this question."`
   This string is **never translated**, ensuring downstream heuristics (`is_unusable_or_negative_reply` and `should_send_sources`) reliably identify ungrounded turns and suppress citations across all languages.
5. **Zero Hardcoded Heuristics**: No language-specific keyword list or if-else routing exists in Python code; all linguistic adherence is steered through system prompt instructions and evaluated via test assertions.

---

## 9. Standalone Visual Verification & Testability

To verify visual math rendering and layout integrity deterministically:
- Dedicated preview routes (such as `/math-preview/summary` and `/math-preview/chat`) render sample papers containing complex multi-line formulas, summations, matrices, and integral equations.
- Headless Chrome (`google-chrome --headless=new --screenshot=...`) captures high-resolution screenshots during automated or manual verification phases to guarantee pixel-accurate rendering across dark and light themes without requiring live model invocations.

---

## 10. Containerization & Cloud Deployment Architecture (Docker & AWS)

The application is structured for containerized cloud deployment on AWS infrastructure:

### 10.1 Multi-Stage Docker Architecture
- **Backend Dockerfile**:
  - Base: `python:3.11-slim` or `python:3.12-slim`.
  - System Dependencies: Installs `tesseract-ocr`, `tesseract-ocr-eng`, `libgl1`, and poppler utilities for PDF OCR processing.
  - Runtime: Non-root user execution running `uvicorn app.main:app --host 0.0.0.0 --port 8000` with production ASGI settings.
- **Frontend Dockerfile**:
  - Base: `node:20-alpine`.
  - Build Stage: Runs `npm ci` and `npm run build` using Next.js standalone output mode (`output: "standalone"` in `next.config.js`).
  - Runner Stage: Copies standalone bundle and static assets, running `node server.js` on port 3000 as a non-root user.

### 10.2 AWS Deployment Topology
- **Compute Layer**:
  - **AWS ECS (Elastic Container Service) with AWS Fargate**: Serverless container execution for backend and frontend services behind an Application Load Balancer (ALB).
  - Alternative: **AWS App Runner** for fully managed auto-scaling container services.
- **Persistence & Storage**:
  - **Relational DB**: Amazon Aurora Serverless PostgreSQL or Amazon RDS PostgreSQL for user authentication and document ownership (migrating from local SQLite `DATABASE_URL`).
  - **Vector Storage**: ChromaDB persisted via Amazon EFS (Elastic File System) volume mount, or migration to Amazon OpenSearch Service / pgvector.
  - **Object Storage**: Amazon S3 for ephemeral PDF temporary staging and cache backups with automated lifecycle expiration policies.
- **Configuration & Secrets**:
  - Secrets (`OPENAI_API_KEY`, `AUTH_SECRET_KEY`) injected securely via AWS Systems Manager Parameter Store or AWS Secrets Manager into container tasks.
  - Environment variables (`LLM_PROVIDER`, `MODEL_NAME`, `MAX_UPLOAD_MB`) configured via ECS task definitions.
- **Edge & Security**:
  - Amazon CloudFront CDN terminating TLS with AWS Certificate Manager (ACM), routing `/api/*` to the backend ALB and all other routes to the Next.js frontend.




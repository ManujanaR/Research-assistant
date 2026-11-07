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

* **Source Actions:**

  * Full-width `+ Research new source` primary button.(One document per session. Upload replaces the current paper).

* **Empty State:**

  * Illustration / Icon (`FileTextOutline`).

  * Text: *"Uploaded sources will appear here."*

  * Drag & Drop zone: Drag-and-drop file listener overlay.

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

## 4.6 Print Report

One button, **Print report**, prints a single document containing the summary and the chat history.

### Document layout

Top to bottom:

1. **Header**
   - "Mitra Research Assistant"
   - The paper's filename
   - "Generated [date]", set when the button is clicked

2. **Summary**
   - The five sections in order, each with its heading:
     1. Title, Authors & Abstract
     2. Problem Statement
     3. Methodology
     4. Key Results
     5. Conclusion

3. **Conversation**
   - Each exchange shown as a *Question* followed by an *Answer*.
   - Numbered citations listed under each answer.
   - Page numbers shown when present.
   - Citations labelled **Retrieved passages**.

4. **Footer**
   - "Answers are grounded in retrieved passages of the uploaded paper. Verify against the source."

### States

| Condition | Behaviour |
|---|---|
| No summary and no messages | Button disabled. Visible reason: "Upload a paper first." |
| Summary loaded, no messages | Print the summary only. Omit the Conversation section. |
| Summary and messages present | Print the full document. |

### Print styling

- Light background, black text, clear heading hierarchy.
- Hide the app shell in print.
- Print styles apply only when printing. The on-screen app is unchanged.

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
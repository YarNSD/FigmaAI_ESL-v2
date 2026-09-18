---
name: figma-blocks
description: >-
  Figma block drawing rules and design system for ESL teaching materials.
  Use when creating or modifying any block on the Figma board.
  Covers colors, typography, spacing, grouping, and required elements.
---

# Figma Blocks Design System Skill

## MANDATORY Elements (every block MUST have)

1. **Background container** — rounded rect, padding 25-40px, visible border
2. **Header bar** — block title + level badge + "Reset" button (right side) + "📑 В МЕНЮ" button
3. **Instruction banner** — soft blue `#eff6ff` strip with 👉 emoji and instruction text in Russian
4. **Hashtags footer** — small 11-12px text, Russian + English tags
5. **Grouping** — ALL elements grouped as one unit for easy canvas dragging
6. **Teacher-Operated Context**: On board, the teacher is the ONLY operator. The student views the teacher's screen share. All font sizes must be large and legible on stream (20-28px), and clickable elements (quiz options, peekaboo covers, reset buttons) are operated by the teacher during verbal dialogue with the student.

---

## Color Tokens (Light Educational Worksheet Theme)

| Token | Hex | Usage |
|-------|-----|-------|
| `bg_block` | `#f8fafc` | Main block sheet background (Slate-50) |
| `bg_card` | `#ffffff` | Inner cards/rows (pure white) |
| `border` | `#cbd5e1` | Crisp outer and card borders (Slate-300) |
| `accent` | `#2563eb` | Primary buttons, headers, accents (Blue-600) |
| `accent_light` | `#3b82f6` | Hover states |
| `button_default` | `#ffffff` | Answer option buttons (white card) |
| `correct` | `#10b981` | Correct answer highlight (Emerald-500) |
| `wrong` | `#ef4444` | Wrong answer highlight (Red-500) |
| `text_primary` | `#0f172a` | All main text (Slate-900 / dark charcoal) |
| `text_secondary` | `#334155` | Subtitles, labels (Slate-700) |
| `text_hashtags` | `#64748b` | Hashtag text (Slate-500) |
| `header_bg` | `#ffffff` | Block header background |

---

## Typography Scale

| Element | Size | Weight | Color |
|---------|------|--------|-------|
| Block title | 26-28px | Bold | #0f172a |
| Section title | 20px | SemiBold | #0f172a |
| Question text | 20-22px | Medium | #0f172a |
| Answer options | 16-18px | Medium | #0f172a (white #ffffff when active correct/wrong) |
| Instruction | 14-16px | Medium | #1e293b (on soft light blue #eff6ff strip) |
| Hashtags | 11-12px | Regular | #64748b |

Font family: **Inter** (Regular / Medium / Bold)

---

## Layout Rules

- `cornerRadius`: 16px for blocks, 12px for inner cards
- `padding`: 24-32px around content
- `itemSpacing`: 16px between elements
- `layoutMode`: VERTICAL for blocks, HORIZONTAL for option rows
- Always use AutoLayout — never absolute positioning for content

---

## Block Naming Convention

Blocks must be named: `{number}.{sub}. {EMOJI} {TYPE}: {TITLE}`

Examples:
- `1.1. 🎯 КВИЗ: IRREGULAR VERBS • PAST SIMPLE CHALLENGE! 🔥`
- `2.1. 🃏 ОТКРЫВАШКИ: FOOTBALL & CATS • GUESS & REVEAL! 🐾`
- `4.3. 📚 СЛОВАРИК: ENGLISH PRONOUNS • 10 МЕСТОИМЕНИЙ`

---

## "В МЕНЮ" Button (required in every block)

- Position: top-right of header
- Text: `📑 В МЕНЮ ↩`
- Background: `#161b22`
- Border: `#30363d`
- Font: 12px Regular
- Action: hyperlink to TOC node (`{ type: "NODE", nodeId: tocId }`)
- Role marker: `role: "back_to_menu"`

---

## Grouping Rule

After creating all elements:
```js
const group = figma.group(allNodes, figma.currentPage);
group.name = blockName;
```

Never leave ungrouped elements on canvas.

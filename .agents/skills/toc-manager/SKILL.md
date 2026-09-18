---
name: toc-manager
description: >-
  Table of Contents management skill for Figma ESL boards.
  Handles creating, updating, and navigating the auto-updating TOC block
  that indexes all learning blocks on the canvas.
---

# TOC Manager Skill

## What is the TOC?

The Table of Contents (TOC) is a special pinned frame on the Figma board
that serves as a navigation index. Every time a new block is created,
a clickable link to it is automatically added to the correct category column.

---

## TOC Structure

```
┌─────────────────────────────────────────────────────────┐
│  📑 ОГЛАВЛЕНИЕ / TABLE OF CONTENTS                      │
│  [🔄 Обновить]                                           │
├──────────┬────────────┬────────┬──────────┬────────┬────┤
│ 🎯 Квизы │🃏 Открывашки│🎬 Видео│📚 Словари│🗂 Карточки│✏️ │
├──────────┼────────────┼────────┼──────────┼────────┼────┤
│ 1.1 → ●  │ 2.1 → ●   │        │ 4.3 → ●  │        │    │
│ 1.2 → ●  │            │        │          │        │    │
└──────────┴────────────┴────────┴──────────┴────────┴────┘
```

---

## Category → Column Mapping

| Block Type | Number & Column Label | Description |
|---|---|---|
| `quiz_photo` | `1.` 🎯 КВИЗЫ | Multiple choice photo quizzes |
| `flip_cards` | `2.` 🃏 ОТКРЫВАШКИ | Flip & peek-a-boo interactive cards |
| `video_quiz` | `3.` 🎬 ВИДЕО | Video listening activities |
| `vocabulary_table` | `4.` 📋 СЛОВАРИ | Lexical reference tables |
| `flashcards` | `5.` 🗂 КАРТОЧКИ | Vocabulary flashcards |
| `fill_blanks` | `6.` ✏️ УПРАЖНЕНИЯ | Gap-fill grammatical tasks |
| `warmup` | `7.` 🏃 РАЗМИНКА | Icebreakers and speaking warmups |
| `timestamp_block` | `8.` 🕒 ТАЙМЛАЙН | Lesson timestamps (full time & date visible) |
| `custom` / misc | `9.` 📌 РАЗНОЕ | Other blocks and notes |

---

## Design System for Navigation Cards (iOS Light Theme)
- **Separate Number Badge**: Placed to the left of the button (`[ 1.1 ]`, `[ 8.1 ]`) with category color border, distinct from the button.
- **Action Button**: Clean white card (`#ffffff`), subtle border (`#e2e8f0`, 1.2px), 12px rounded corners, iOS chevron `›` on the right.
- **No Truncation / No Abbreviations**: Block titles are wrapped across lines without cutting off words or using ellipses (`...`).
- **Full Date & Time in Timeline**: Timestamps in `ТАЙМЛАЙН` display `🕒 {time}` and `📅 {full date}` completely.

---

## TOC Identification

The TOC frame is identified by its name starting with `__ESL_TOC__`.
Always search by this marker, NOT by position on canvas.

---

## Adding an Entry

When a block is created:
1. Find TOC by `__ESL_TOC__` marker
2. Determine category column from block_type
3. Create a text node: `{blockTitle}` with hyperlink to block NodeId
4. Append to the correct column
5. Adjust column height if needed

## Creating TOC from scratch

If TOC doesn't exist:
1. Create at position (0, -500) — above the main content area
2. Width: 1400px, height: auto (HUG)
3. Name: `__ESL_TOC__ 📑 ОГЛАВЛЕНИЕ`
4. Create 7 columns with headers
5. Pin to top of viewport (not fixed, just place it there)

---

## Navigation Links

Each TOC entry must be a text with hyperlink:
```js
textNode.hyperlink = {
  type: "NODE",
  value: targetNodeId
};
```

This enables one-click navigation to any block on the canvas.

---

## Full Refresh Logic

`REFRESH_TOC` command:
1. Delete all existing entries from all columns (keep headers)
2. Scan `figma.currentPage.children` for all nodes with `role` metadata
3. Sort by creation order
4. Re-add all entries to correct columns

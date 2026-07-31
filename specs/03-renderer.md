# Spec 03: Docx Renderer

## Goal
Turn selected bank data plus a profile into a .docx that matches the golden
template exactly. Deterministic: same input always yields the same bytes.

## Module
`src/jobengine/resume/render.py`. Template at
`resume/templates/golden.docx`.

## Typography spec

Extracted from the user's Word template. These are exact.

| Element | Font | Size | Bold | Italic | Align | Spacing |
|---|---|---|---|---|---|---|
| Name | Arial | 14pt | yes | no | center | 1.15 |
| Contact line | Arial | 12pt | no | no | center | 1.15 |
| Status/location line | Arial | 12pt | no | no | center | 1.15 |
| Section headers | Arial | 10.5pt | yes | no | left | 1.5 |
| Job title line | Arial | 10.5pt | no | **yes** | left | 1.5 |
| Date (same line) | Arial | 10.5pt | no | **yes** | right tab | 1.5 |
| Bullets | Arial | 10.5pt | no | no | left | 1.5 |

Page: US Letter, margins 0.5in (720 twips) on all four sides.

**Tab stop: exactly one right tab at 7.5in (10800 twips).** The source
template has three inconsistent tab stops (7.5in, 6.5in, and a center tab at
6.8in), which is why dates do not line up. Normalize to one.

**Alignment: left, not justified.** The source template uses justified
(`w:jc="both"`). Change it.

Colors: black only, except phone, email, and link runs which may be blue.

## Structure

```
[Name]                                          center, 14pt bold
[Phone | Email | LinkedIn | GitHub | Portfolio | Scholar]   center, 12pt
[Work authorization statement | State]          center, 12pt
<single blank line>
[Summary]                                       only if profile requires it
Education & Certificates                        bold header
  • degree bullets                              max 3 lines total
<single blank line>
Work History                                    bold header
  [Title at Company, State]          [Mon YYYY to Mon YYYY]   italic both
    • summary bullet
    • What/How/Result bullet x2-7
  <single blank line between roles>
Projects                                        bold header, same shape
Publications                                    bold header, plain bullets
```

## Rules

1. **Section order is profile-driven.** Per Lee, when the target title does
   not require a degree or the degree would make you look overqualified,
   Education moves to the bottom. Read from the profile config, not hardcoded.
2. **Summary section only when triggered.** Lee lists exactly three triggers:
   changing industries, relocating, or visa/sponsorship. Otherwise omit
   entirely. The work-authorization line in the contact block already covers
   the visa case for this user; do not duplicate it.
3. **Dates.** Full-time and internships require Month and Year. Projects
   require neither. Current roles render "to Present".
4. **Publications** render as plain bullets with the author-name run bolded
   and nothing else. The section header is bold, not bold-italic.
5. Never bold anything inside a section except the section header itself.
6. Rendering must not mutate the template file.

## PDF

Render .docx, then convert with LibreOffice headless. In the sandbox use the
wrapper described in the pptx skill rather than bare `soffice`, which hangs.
The PDF is what gets uploaded; the .docx is kept for editing.

## Watermarking

When any selected bullet has `status: speculative`, the render must:
- take the `preview` code path
- stamp a diagonal "DRAFT - CONTAINS UNBUILT WORK" watermark
- write to `resume/rendered/preview/` and never to the outbound directory

## Golden test

`tests/test_render.py` renders the full bank with no tailoring and compares
against `tests/fixtures/golden.docx` on: font names, all `w:sz` values,
`w:spacing` values, `w:jc` values, tab stop positions, and page margins.
Compare the parsed XML properties, not the raw bytes, since docx zips are not
reproducible byte-for-byte.

## Definition of done
The golden test passes, and opening the output in Word side by side with the
user's template shows no visible difference except the three deliberate fixes
(left alignment, single tab stop, added summary bullets).

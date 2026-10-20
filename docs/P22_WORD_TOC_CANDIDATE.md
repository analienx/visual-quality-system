# P22 — bounded native Word TOC candidate repair

P21 found missing native table-of-contents bookmark targets in an actual,
private Contoso DOCX. P22 gives Microsoft Word exactly one recognized TOC to
update, saves it as a **new disposable** DOCX and refuses to overwrite the
original. This is a narrow repair, not a declaration that G5 or G6 passed.

## Run on a Windows client with Microsoft Word

An exclusive Word session is required. Start with an existing local source and
choose **unused** private output names:

```powershell
python -m scripts.word_p22_toc_candidate .\source.docx `
  --candidate .\candidate-updated.docx --output .\candidate-receipt.json
```

The native automation opens the exact source in Word read-only, verifies that
Word recognizes one TOC, calls the supported `TableOfContents.Update()` and
uses `SaveAs2` only for the private candidate. Existing Word instances, absent
TOCs, missing source defects, unsupported OOXML, uncertain process identity,
occupied destinations and contradicted receipts block the operation.

The Python gate checks:

1. Original source SHA-256 and inventory are unchanged before and after,
   including after exclusive creation of the candidate.
2. Exactly one TOC remains, all previously unresolved internal bookmark
   targets resolve, and the logical main-story table group count is unchanged.
3. **Exact ordered heading strings and all table-cell strings** have the same
   SHA-256 and count. Private content remains in private files.
4. Other direct body-paragraph text changes are *reported* by hunk count and
   require **independent prose review**. Word can legitimately normalize field
   result XML, but this check does not certify the rest of the document.
5. A failed operation removes only a candidate that this process actually
   created. It does not clean up or kill other Word sessions.

The receipt intentionally keeps native PDF review, rendered field integrity,
document/report consistency and independent acceptance in `blocked` state.
A timed-out COM automation process may require a **PID-verified run-owned**
cleanup; never terminate Word processes indiscriminately.

## Real native pilot (2026-10-19, diagnostic only)

A disposable copy of the actual Contoso report was processed with Microsoft
Word. The original source hash remained identical. The regenerated candidate
contained **45 bookmark definitions**, **45 internal links** and **zero
unresolved links**. All **45 headings** and **1,561 table-cell strings** remained
identical; Word still recognized **42 logical tables**. Its PDF lacked the
previous English broken-bookmark error text.

But this is **not** a full success: Word reported **32 pages**, while the
diagnostic PDF contained **31 physical pages**. The mismatch must remain a
visible failed/blocked pagination consistency gate; some non-table paragraph
markup was rewritten and the document still contains owner placeholders.
Microsoft documents the [Word TOC updater](https://learn.microsoft.com/en-us/office/vba/api/word.tableofcontents.update)
and [full-document PDF export](https://learn.microsoft.com/en-us/office/vba/api/word.document.exportasfixedformat).
Word section breaks can affect its page-number model and must be inspected,
not masked by simply decrementing the count.

## Required downstream review

- Run P17 on the exact candidate with a source-bound, physically reconciled
  PDF page count; run P19/P21 on **every** page and validate all bookmark links,
  blank/overflow pages, recognized field errors and source hashes.
- Have a separate reviewer inspect the complete document, TOC navigation,
  changed prose, page breaks, visuals, tables, images, source figures and
  remaining template placeholders.
- Keep G2/G4/G5/G6 blocked until separately witnessed and owner-authorized;
  never promote this candidate to the user's original DOCX automatically.

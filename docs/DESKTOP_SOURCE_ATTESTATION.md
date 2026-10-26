# Exact Power BI Desktop loaded-source attestation

This optional **G0 evidence guard** supports issue [#16](https://github.com/analienx/visual-quality-system/issues/16). It helps prevent an interaction receipt from being assigned to the wrong open PBIP. It does **not** establish G2 aesthetics, G4 interaction correctness, or independent G6 release approval.

Run on the authorized Windows host using a **disposable, already-open, saved** PBIP containing exactly one wrapper and its matching report folder. The identity collector supports unrelated report projects; the DAX/UIA runners shown below remain Contoso-specific. Use a unique output file under an ignored/private evidence directory; do not commit raw run receipts, model cache, window captures, or user paths.

```console
python -m scripts.desktop_source_attestation DISPOSABLE_PROJECT --desktop-pid PID --output PRIVATE/desktop-source.json
python -m scripts.contoso_p14_live_oracle DISPOSABLE_CONTOSO_PROJECT --desktop-pid PID --attest-loaded-file --output PRIVATE/dax-oracle.json
python -m scripts.contoso_p16_native_interaction DISPOSABLE_CONTOSO_PROJECT --desktop-pid PID --oracle PRIVATE/dax-oracle.json --attest-loaded-file --output PRIVATE/native-uia.json
```

All three commands are **read-only with respect to report source**; the UIA runner changes supported **in-memory filter selections** and restores the Year state. It never saves or publishes the report. Never use the UIA runner against an open user editing session.

The attestor accepts only all of the following: a real OS `PBIDesktop.exe` with exact PID and exactly one launched PBIP argument matching the discovered physical project; a **single** native Desktop Bridge registry entry matching the expected `.Report` folder and same PID; ready Bridge status; explicit `hasUnsavedChanges: false`; and report files not modified after that process was started. Disagreements block **before** the DAX or UIA action in strict mode. Missing psutil/CLI/registry/permissions also block. Because Desktop may mark a refreshed model unsaved, a legitimate session can remain blocked until its state is resolved safely; do **not** force-save or relax the flag to obtain a green verdict.

The physical source/model digest is still inventoried before and after DAX/UIA. The attestation is evidence of **launch/registered loaded file identity at inspection time**, not cryptographic proof of inaccessible Desktop process memory or that the host was independently reviewed. Independent reviewers must inspect the source-bound private receipts and screenshots; no automating agent should sign its own G6.

The collector **does not contact Bridge at all** if the requested PID's OS command line names an unrelated PBIP. A live negative probe on 26 October 2026 correctly rejected the existing user-protected Desktop process as a different project without interacting with it.

**Acceptance still open:** UIA shapes/country map, interactions on a second unrelated PBIP, authenticated Corporate Spend map, and an independent release reviewer/publisher (see #16 and #80). The flag is opt-in to preserve the historical limited engineering contract; any new production-release evidence request must enable it and cannot treat a default legacy receipt as attested.

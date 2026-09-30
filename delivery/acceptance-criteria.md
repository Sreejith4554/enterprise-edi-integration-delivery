# UAT acceptance checklist

Record tester, date, commit and correlation IDs when executing.

- [ ] Fresh checkout configures and starts the real Compose stack.
- [ ] /health reports API/database/broker ready; consumer connected.
- [ ] JSON order reaches COMPLETED with matching canonical values, ERP ID and acknowledgement.
- [ ] EDI order reaches the same canonical contract and includes ORDRSP-style response.
- [ ] Invalid JSON, invalid SKU and malformed EDI create inspectable failed messages.
- [ ] Repeating a business order creates a duplicate failure and no extra ERP effect.
- [ ] Correcting invalid input keeps correlation ID and previous raw text in audit.
- [ ] ERP outage becomes a technical failure; recovery plus explicit retry completes it.
- [ ] Retry limit and terminal duplicate rules hold.
- [ ] History filters/pagination and dashboard detail allow an independent reviewer to trace messages.
- [ ] Automated checks and live smoke evidence are available; limitations are acknowledged.

Do not tick this template without running the checks. Automated execution evidence is separate in CI artifacts and docs/verification.md.

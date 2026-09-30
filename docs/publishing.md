# Publish and complete infrastructure verification

The requested repository is https://github.com/Sreejith4554/enterprise-edi-integration-delivery. It was empty when inspected. The connected integration could read it but its content-write attempt returned 403. The delivered ZIP therefore contains the complete repository tree, including dotfiles and CI, without local credentials/databases/caches.

Extract the archive. In its `enterprise-edi-integration-delivery` directory:

```bash
git init -b main
git add .
git commit -m "Implement enterprise EDI integration delivery platform"
git remote add origin https://github.com/Sreejith4554/enterprise-edi-integration-delivery.git
git push -u origin main
```

Authenticate with your own authorized GitHub account/credential manager. Configure Git author identity if prompted. If the remote has acquired commits since this package was prepared, clone it first, copy the project files into that checkout, inspect the diff and commit normally; do not force-push over other work.

Alternatively, grant the GitHub integration **Contents: read/write** and, for the workflow file, appropriate **Workflows** write permission. Repository admin status alone did not authorize the attempted app write. No credential should be pasted into chat or committed.

After push, inspect Actions → integration-ci. Require lint, 43 tests and real Compose smoke including ERP outage/recovery to pass. Download integration-verification artifacts, review verification-local.json and compose.log, and update docs/verification.md with the actual run link and results. A workflow file existing in a repository is not evidence that it passed.

For local verification:

```bash
python scripts/configure.py
docker compose up --build -d --wait --wait-timeout 180
python -m pip install -r requirements.lock
python -m pytest -q
python scripts/smoke.py --chaos
```

These commands require Docker Compose and image/package download access. A failed infrastructure check must be diagnosed and fixed before release acceptance. Do not mark the UAT/release template complete automatically.

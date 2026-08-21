# Deployment Runbook

This documents the deployment completed for the Flexbone OCR API.

## Deployed resources

| Resource | Value |
| --- | --- |
| GCP project | `flexbone-ocr-challenge-505909` |
| Region | `asia-south1` |
| Cloud Run service | `flexbone-ocr` |
| Runtime service account | `ocr-runtime@flexbone-ocr-challenge-505909.iam.gserviceaccount.com` |
| Artifact Registry repository | `flexbone` |
| Production configuration secret | `flexbone-ocr-env` |
| GitHub repository | `therealahnaf/flexbone-ocr` |
| Public API | `https://flexbone-ocr-7wgxo2mfka-el.a.run.app` |

## 1. Authenticate and select the project

```powershell
gcloud auth login
gcloud auth application-default login
gcloud config set project flexbone-ocr-challenge-505909
gcloud config get-value project
```

`gcloud auth login` authorizes CLI operations. Application Default Credentials
authorize Google client libraries during local development without downloading a
service-account key.

## 2. Enable required APIs

```powershell
gcloud services enable `
  vision.googleapis.com `
  run.googleapis.com `
  cloudbuild.googleapis.com `
  artifactregistry.googleapis.com `
  secretmanager.googleapis.com `
  iam.googleapis.com `
  billingbudgets.googleapis.com
```

Only APIs used by the application and delivery pipeline were enabled. Vision
performs OCR; the remaining APIs build, store, configure, and run the service.

## 3. Create the runtime identity

```powershell
gcloud iam service-accounts create ocr-runtime `
  --display-name="OCR API Runtime"
```

The Cloud Run container uses this dedicated identity instead of a default service
account or credential file. It was granted only Service Usage Consumer and access
to the production configuration secret.

## 4. Store production configuration

The application reads local `.env` by default. In Cloud Run it reads the file
selected by:

```text
OCR_ENV_FILE=/secrets/ocr.env
```

The production dotenv document was stored as version 1 of `flexbone-ocr-env` and
mounted read-only at `/secrets/ocr.env`.

```powershell
gcloud secrets create flexbone-ocr-env `
  --replication-policy=automatic `
  --data-file=.env.example

gcloud secrets add-iam-policy-binding flexbone-ocr-env `
  --member="serviceAccount:ocr-runtime@flexbone-ocr-challenge-505909.iam.gserviceaccount.com" `
  --role="roles/secretmanager.secretAccessor"
```

One versioned dotenv secret keeps production configuration out of Git, images,
and build logs while remaining simple and within the small-project free allowance.
Google credentials are not stored in it because Cloud Run supplies ADC through
the runtime service account.

## 5. Create the image repository

```powershell
gcloud artifacts repositories create flexbone `
  --location=asia-south1 `
  --repository-format=docker `
  --description="Flexbone OCR production images"
```

Artifact Registry and Cloud Run use the same region to avoid unnecessary transfer.
Images are tagged with the Git commit SHA so every deployment is traceable.

The policy in `deploy/artifact-registry-cleanup-policy.json` deletes images older
than seven days while retaining the newest three. It was inspected in dry-run mode
before deletion was enabled to control storage without removing rollback images.

## 6. Separate CI and deployment permissions

Two service accounts were created:

- `flexbone-ci`: Logs Writer only; it runs untrusted pull-request tests.
- `flexbone-deployer`: Logs Writer, Service Usage Consumer, Cloud Run Admin,
  Artifact Registry Writer, and permission to attach `ocr-runtime`.

Separating these identities prevents pull-request code from receiving production
deployment or secret privileges. Neither account can read the secret payload.

## 7. Publish and connect GitHub

```powershell
gh repo create therealahnaf/flexbone-ocr `
  --public `
  --source . `
  --remote origin `
  --push
```

The repository is public for challenge review. The Cloud Build GitHub App was then
connected once through the GCP console.

## 8. Configure CI/CD

Two global Cloud Build triggers are active:

| Trigger | Event | Configuration | Identity |
| --- | --- | --- | --- |
| `flexbone-pr-ci` | Pull request to `main` | `cloudbuild-ci.yaml` | `flexbone-ci` |
| `flexbone-main-deploy` | Push to `main` | `cloudbuild-deploy.yaml` | `flexbone-deployer` |

Pull-request CI runs frozen dependency installation, Ruff, formatting checks, and
tests with at least 85% coverage. It uses a fake OCR provider, so CI consumes no
Vision quota.

After CI passes and a pull request merges, the deployment trigger:

1. Repeats all quality checks so deployment cannot bypass CI.
2. Builds and pushes an image tagged with `$COMMIT_SHA`.
3. Deploys the image with numeric secret version `_OCR_ENV_VERSION=1`.
4. Calls `/api/v1/health` and fails the build if the service is unhealthy.

`main` requires the `flexbone-pr-ci` check, current branches, linear history, and
resolved conversations. Force pushes and branch deletion are disabled.

## 9. Cloud Run settings

```text
CPU: 1
Memory: 512 MiB
Request timeout: 60 seconds
Concurrency: 20
Minimum instances: 0
Maximum instances: 1
Authentication: public
Billing: request-based with CPU throttling
```

Scale-to-zero limits idle cost. Maximum one instance keeps the in-memory cache and
rate limiter consistent for this challenge. The service runs as the non-root user
defined in the Dockerfile and receives `PORT` from Cloud Run.

## 10. Cost controls and verification

A `$1` monthly budget sends alerts at 50%, 90%, and 100%. Artifact cleanup is
active, and paid container vulnerability scanning was not enabled.

The completed deployment was verified with:

- Local Ruff, formatting, and 26 tests at approximately 99% coverage.
- A non-root local container using a read-only mounted dotenv file.
- Successful Cloud Build CI and deployment builds.
- Public health and OpenAPI documentation.
- Live JPEG, PNG, GIF, duplicate-cache, and ordered batch OCR requests.

## Rotate configuration

```powershell
gcloud secrets versions add flexbone-ocr-env --data-file=NEW_ENV_FILE
```

Update `_OCR_ENV_VERSION` on `flexbone-main-deploy`, then run the trigger. Numeric
versions make configuration deployments reproducible. Keep the current and two
previous versions enabled for rollback; destroy older versions after verification.
Never print the payload or place it directly in shell arguments.

## Roll back

```powershell
gcloud run revisions list `
  --service=flexbone-ocr `
  --region=asia-south1

gcloud run services update-traffic flexbone-ocr `
  --region=asia-south1 `
  --to-revisions=PREVIOUS_REVISION=100
```

Cloud Run revisions retain their immutable image and pinned secret version, so
moving traffic restores both application code and configuration together.

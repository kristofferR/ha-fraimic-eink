# Daily source checks

The **Daily source checks** GitHub Actions workflow runs every day at 06:23 UTC
and can be started manually from the Actions tab. It discovers sources from the
integration's provider registry, fetches candidates through the real provider
code, and downloads and decodes an image. Empty results, parsing failures,
download errors, and invalid images fail the check.

Checks run with at most four sources at once and a three-minute limit per source.
The normal provider request throttles and image-size limits still apply. If any
sources fail, the job waits 30 minutes and retries only those sources once, with
fresh sessions and caches. A recovered source passes; any source still failing
makes the job fail. The job summary lists every source's final result, including
recoveries and skips. These checks do not display images or modify any frames.

Configure these repository Actions secrets for sources that use API keys:

| Secret | Source | Without the secret |
|---|---|---|
| `UNSPLASH_ACCESS_KEY` | Unsplash | Explicitly skipped |
| `PEXELS_API_KEY` | Pexels | Explicitly skipped |
| `NASA_API_KEY` | NASA APOD | Uses the provider's public `DEMO_KEY` |
| `SMITHSONIAN_API_KEY` | Smithsonian | Uses the provider's public `DEMO_KEY` |

Missing required keys appear as skips in both the log and summary. A configured
key that stops working fails like any other provider error. Secrets are passed
only as environment variables and redacted from reported errors.

Run the same checks locally:

```bash
uv run scripts/check_sources.py
# Check one source and retry immediately while developing:
uv run scripts/check_sources.py --providers reframed --retry-delay 0
```

Ordinary pytest runs remain offline. `tests/test_source_checks.py` verifies the
retry timing, retry selection, image validation, redaction, and CI exit status
without waiting or contacting external services.

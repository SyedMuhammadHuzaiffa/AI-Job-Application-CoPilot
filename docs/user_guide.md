# User Guide

## Apply Tab

Paste a job description, generate a tailored draft, review every claim, export `.tex` files, and save the opportunity to the tracker.

The app never submits applications. `Ready to Apply` requires human approval checkboxes.

## Profile Tab

Use `Generate Enhanced Profile` to migrate `profile.json` or `profile.yaml` into the advanced schema. Missing information is left empty. The completeness dashboard shows missing fields, warnings, recommended additions, and factual enrichment suggestions.

## Job Discovery Tab

Use filters to find junior, graduate, internship, remote, UAE, Pakistan, and sponsorship-friendly roles. `Huzaifa Mode` boosts UAE sponsorship, remote software roles, Pakistan software roles, and Europe sponsorship roles.

Save jobs or mark them Applied, Interviewing, Rejected, or Offer. Marking a discovered job can import it into the tracker.

Marking a job `Applied` requires confirming that you personally submitted it.

## Guided Assistant Tab

Use the `Guided Assistant` tab after saving a job from Job Discovery.

The assistant creates an application packet with:

- tailored CV and cover letter paths
- downloadable CV and cover letter PDFs
- common application answers
- LinkedIn outreach messages
- copy buttons for profile fields and prepared answers
- a safety checklist

Use `Open application page` to open the job site. Copy prepared fields manually. Stop at login, account creation, CAPTCHA, or final submit unless you personally decide to continue on the job site.

The assistant does not mass-apply, auto-submit, create fake accounts, or invent missing profile facts. `Applied` status requires your explicit confirmation.

## Resume Intelligence Tab

Paste a job description and review or replace the profile-derived CV text. The engine scores match quality, finds keyword gaps, ranks projects, suggests skill focus, rewrites the summary truthfully, and recommends whether to apply.

## Dashboard and Analytics

The dashboard shows status counts. The Analytics tab tracks applications sent, interviews, rejections, offers, response rate, interview rate, and offer rate. It also provides breakdowns by country, company, role, source, and month.

## Settings Tab

Use Settings to inspect:

- selected model
- profile file path
- environment validation
- cache status
- retry attempts
- resolved data/export/template paths

If `OPENAI_API_KEY` is missing, generation features will fail gracefully and non-LLM features still work.

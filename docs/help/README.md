# Help pages

These are the site's help pages, served at `/help/<name>` (e.g. `faq.md` at
`/help/faq`) with an index at `/help`. Like the policies in `docs/policies/`,
they're loaded into the site wiki by `scripts/init_policy_wiki_pages.py`
(which the installer runs) and use the same placeholders: `{{SITE_NAME}}`,
`{{DOMAIN}}`, `{{SITE_URL}}`, `{{OPERATOR}}` and `{{GOVERNING_LAW}}`,
filled in from /admin/site.

Existing pages aren't overwritten on a re-run. After changing these files,
reload them with:

    sudo env FORCE_POLICY_IMPORT=1 tippr-run /home/tippr/src/tippr/scripts/init_policy_wiki_pages.py

or edit a page on the site at /wiki/help/<name> (as an admin).

To add a page, add a `.md` file here (its first `# heading` is its title)
and its name to `HELP_PAGES` in `r2/r2/controllers/policies.py`.

Keep them generic: no site names, addresses or email addresses (link to
`/contact#<section>` for anything people should send to the admins).

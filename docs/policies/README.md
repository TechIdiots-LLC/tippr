# Legal Policies Documentation

This directory contains the legal policy documents for Tippr, including:

- **Terms of Use / User Agreement** - [TERMS_OF_USE.md](TERMS_OF_USE.md)
- **Privacy Policy** - [PRIVACY_POLICY.md](PRIVACY_POLICY.md)
- **Content Policy** - [CONTENT_POLICY.md](CONTENT_POLICY.md)
- **Moderator Guidelines** - [MODERATOR_GUIDELINES.md](MODERATOR_GUIDELINES.md)

## Overview

These policies are designed following open-source best practices, inspired by templates from:

- [Discourse](https://discourse.org) (CC BY-SA)
- [Automattic/WordPress](https://github.com/Automattic/legalmattic) (CC BY-SA)
- [Mastodon](https://joinmastodon.org)

All policy documents are released under the **Creative Commons Attribution-ShareAlike 4.0 International License (CC BY-SA 4.0)**, allowing you to adapt them for your own use.

## Key Features

### User Agreement (Terms of Use)

The User Agreement covers:

- **User-Generated Content License** (Section 4): Users retain ownership but grant Tippr a license to display content
- **Moderator Status** (Section 6): Clarifies that moderators are volunteers, not employees
- **Section 230 Notice** (Section 12): Important legal protection for platform operators

### Privacy Policy

The Privacy Policy covers:

- **Information Collection**: What data is collected and how
- **Data Usage**: How user data is used
- **User Rights**: CCPA and GDPR compliance sections
- **Cookie Policy**: Detailed cookie information

### Content Policy

The Content Policy covers:

- **Prohibited Content**: Illegal content, harassment, hate speech, spam
- **Prohibited Behavior**: Ban evasion, brigading, report abuse
- **Enforcement**: How violations are handled

### Moderator Guidelines

The Moderator Guidelines cover:

- **Volunteer Status**: Clarifies moderators are not employees
- **Code of Conduct**: Expected behavior for moderators
- **Moderation Tools**: Available tools and how to use them
- **Best Practices**: Community building and handling difficult situations

## Setup

### Initializing Wiki Pages

After setting up your Tippr instance, run the initialization script to populate the wiki pages:

```bash
python scripts/init_policy_wiki_pages.py
```

This will create wiki pages at:
- `/help/useragreement`
- `/help/privacypolicy`
- `/help/contentpolicy`
- `/help/moderatorguidelines`

### Configuration

The wiki page names are configurable in your `*.ini` file:

```ini
wiki_page_content_policy = contentpolicy
wiki_page_privacy_policy = privacypolicy
wiki_page_user_agreement = useragreement
wiki_page_moderator_guidelines = moderatorguidelines
```

### Editing Policies

After initialization, you can edit the policies through:

1. **Wiki Interface**: Navigate to `/wiki/edit/[pagename]`
2. **Direct File Edit**: Modify the files in `docs/policies/` and re-run the init script

## Moderator Welcome Message

When users become moderators (either by direct addition or by accepting an invitation), they automatically receive a welcome message that includes:

- Congratulations and welcome
- Overview of moderator responsibilities
- Links to important resources (Moderator Guidelines, Content Policy, User Agreement)
- Reminder about volunteer status

This message is defined in `r2/r2/lib/system_messages.py`.

## Customization

The files here are templates. When the installer creates the wiki pages
(`scripts/init_policy_wiki_pages.py`), it fills in these placeholders from
the site's settings on `/admin/site`:

| Placeholder | Filled with | When it isn't set |
|---|---|---|
| `{{SITE_NAME}}` | the site name | the domain |
| `{{DOMAIN}}`, `{{SITE_URL}}` | the site's domain and address | |
| `{{OPERATOR}}` | the operator (who runs the site, by legal name) | the site name |
| `{{GOVERNING_LAW}}` | the governing law, e.g. "the State of New York" | "the place where the site's operator is established" |

Where the policies tell people how to reach the site, they link to a
section of the site's contact page (`/contact#privacy`, `#legal`, `#appeals`,
`#report-content`, `#moderators`), which offers a message to the admins and,
where one is set, an email address. That works on any domain, and nobody's
address is built into the text.

Set those before the pages are created, or rebuild the pages afterwards
(this replaces edits made on the wiki):

```bash
sudo env FORCE_POLICY_IMPORT=1 tippr-run /home/tippr/src/tippr/scripts/init_policy_wiki_pages.py
```

Existing pages are never changed otherwise, so editing them on the wiki
(`/wiki/useragreement` and so on) is safe. Still:

1. **Review the jurisdiction**: the policies are written with US law in
   mind; adapt them if you're elsewhere.
2. **Add specific rules** for your community.

## Legal Disclaimer

These policy templates are provided as a starting point and should be reviewed by legal counsel before use. They may not address all legal requirements for your specific jurisdiction or use case.

## License

All policy documents in this directory are released under the [Creative Commons Attribution-ShareAlike 4.0 International License (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/).

You are free to:
- **Share** — copy and redistribute the material in any medium or format
- **Adapt** — remix, transform, and build upon the material for any purpose, even commercially

Under the following terms:
- **Attribution** — You must give appropriate credit
- **ShareAlike** — If you remix, transform, or build upon the material, you must distribute your contributions under the same license

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

When customizing these policies for your instance:

1. **Update Contact Information**: Replace `legal@tippr.net`, `privacy@tippr.net`, etc. with your actual contact emails
2. **Update Company Name**: Replace "TechIdiots LLC" with your company name
3. **Update Domain**: Replace "tippr.net" with your domain
4. **Review Jurisdiction**: The policies reference Massachusetts law and US regulations; update for your jurisdiction if different
5. **Add Specific Rules**: Add any additional rules specific to your community

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

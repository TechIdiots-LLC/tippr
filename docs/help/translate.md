# Translating {{SITE_NAME}}

{{SITE_NAME}} is powered by Tippr, an open-source platform, and supports multiple languages. You can select your preferred language in your [preferences](/prefs/). Languages marked with an asterisk (*) are partially translated and may still display some text in English.

All translations are maintained centrally in the [tippr-i18n project on GitHub](https://github.com/TechIdiots-LLC/tippr-i18n). Because translations are built into the core software, any updates or improvements made there automatically roll out to every site powered by Tippr with its next update.

## Fix or complete a translation

Each language is contained in a single file:

    tippr_i18n/<language>/LC_MESSAGES/r2.po

You can edit this file directly on GitHub or with any PO editor (such as [Poedit](https://poedit.net/) or [Lokalize](https://apps.kde.org/lokalize/)).

1. Review the project's [README](https://github.com/TechIdiots-LLC/tippr-i18n/blob/master/README.txt) for formatting guidelines (for example, keeping placeholders like `%(name)s` exactly as they are in English).
2. Make your edits.
3. Submit a [pull request](https://github.com/TechIdiots-LLC/tippr-i18n/pulls).

Contributing directly requires a free GitHub account.

## Report a translation issue

If you notice an incorrect or awkward translation but prefer not to edit the file yourself, please [open an issue](https://github.com/TechIdiots-LLC/tippr-i18n/issues/new) on GitHub (this also needs a free GitHub account).

To help us fix it quickly, please include:

- the language
- the page where it appears
- the current text, and what it should say

A screenshot helps too.

# Contributing

## Licence headers

tippr is reddit's code plus TechIdiots LLC's work, under the Common Public
Attribution License (see [LICENSE](LICENSE)). Each source file says which it
is:

- **Files from reddit** (and files ported from them, such as the pure Python
  fallbacks for the `.pyx` modules) keep reddit's header, naming reddit as
  the Original Code and adding our line:

  ```
  # Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026
  # TechIdiots LLC. All Rights Reserved.
  ```

- **Files written for tippr** use tippr's header:

  ```
  # The contents of this file are subject to the Common Public Attribution
  # License Version 1.0 (the "License"); you may not use this file except in
  # compliance with the License. You may obtain a copy of the License at
  # https://github.com/TechIdiots-LLC/tippr/blob/master/LICENSE.
  #
  # Software distributed under the License is distributed on an "AS IS" basis,
  # WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
  # the specific language governing rights and limitations under the License.
  #
  # The Original Code is Tippr.
  #
  # The Initial Developer of the Original Code is TechIdiots LLC.
  # Copyright (c) 2026 TechIdiots LLC. All Rights Reserved.
  ###############################################################################
  ```

  Mako templates use the same text with `##` in place of `#`; JavaScript
  and LESS use `//`. A shebang (or a Dockerfile's `# syntax=` line) stays
  first.

- **Generated files** (such as the Thrift stubs) and **configuration**
  (systemd units, workflow YAML, `pyproject.toml`, `.env` examples) don't
  get a header.

Don't start a new file by copying an existing one's header without checking
which kind it is.

## Changes

Note user-visible changes in [CHANGELOG.md](CHANGELOG.md) under `master`.
Releases are described in [docs/RELEASING.md](docs/RELEASING.md).

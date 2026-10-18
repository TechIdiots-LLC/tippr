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
"""Labels for how much AI went into a post.

- Every new post says whether it is human-made, AI-assisted or AI-generated
  (Link.ai_content). Posts from before labels existed have no label and are
  treated as unlabelled, not as AI.
- A vault's moderators choose which labels it accepts (Vault.ai_policy).
- Each user chooses what to see (Account.pref_ai_content).

Labels are what the poster says; nothing tries to detect AI. Mislabelled
posts are for reports and moderators.
"""

from pylons.i18n import N_

HUMAN = "human"
ASSISTED = "assisted"
GENERATED = "generated"
LABELS = (HUMAN, ASSISTED, GENERATED)

LABEL_NAMES = {
    HUMAN: N_("human-made"),
    ASSISTED: N_("AI-assisted"),
    GENERATED: N_("AI-generated"),
}

LABEL_HELP = {
    HUMAN: N_("made by people, without AI"),
    ASSISTED: N_("made by people with some AI help (editing, fixes, ideas)"),
    GENERATED: N_("mostly or entirely made by AI"),
}

# vault policies
POLICY_ANY = "any"
POLICY_NO_GENERATED = "no_generated"
POLICY_AI_ONLY = "ai_only"
POLICIES = (POLICY_ANY, POLICY_NO_GENERATED, POLICY_AI_ONLY)

POLICY_LABELS = {
    POLICY_ANY: LABELS,
    POLICY_NO_GENERATED: (HUMAN, ASSISTED),
    POLICY_AI_ONLY: (ASSISTED, GENERATED),
}

POLICY_NAMES = {
    POLICY_ANY: N_("any posts (labelled)"),
    POLICY_NO_GENERATED: N_("no AI-generated posts"),
    POLICY_AI_ONLY: N_("AI-assisted and AI-generated posts only"),
}

# user preferences
PREF_SHOW = "show"
PREF_HIDE_GENERATED = "hide_generated"
PREF_HIDE_AI = "hide_ai"
PREFS = (PREF_SHOW, PREF_HIDE_GENERATED, PREF_HIDE_AI)

PREF_NAMES = {
    PREF_SHOW: N_("show everything (with labels)"),
    PREF_HIDE_GENERATED: N_("hide AI-generated posts"),
    PREF_HIDE_AI: N_("hide AI-generated and AI-assisted posts"),
}

PREF_HIDDEN_LABELS = {
    PREF_SHOW: (),
    PREF_HIDE_GENERATED: (GENERATED,),
    PREF_HIDE_AI: (ASSISTED, GENERATED),
}


def allowed_labels(policy):
    """The labels a vault with this policy accepts."""
    return POLICY_LABELS.get(policy, LABELS)


def hidden_labels(user):
    """The labels this user has chosen not to see (none when logged out)."""
    pref = getattr(user, "pref_ai_content", PREF_SHOW) if user else PREF_SHOW
    return PREF_HIDDEN_LABELS.get(pref, ())


def is_hidden(user, link):
    """Whether the user's preference hides this post."""
    label = getattr(link, "ai_content", None)
    return bool(label) and label in hidden_labels(user)

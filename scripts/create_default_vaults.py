"""Create the starter vaults and make the front page defaults.

Run with tippr-run (install/tippr.sh does this on every install):

    tippr-run scripts/create_default_vaults.py

The defaults lean toward technology, science, making things and fun. News
and politics vaults exist but aren't defaults, so they don't fill the front
page unless people subscribe. Creative vaults take human-made and AI-assisted
posts, with separate vaults for AI-generated art and music.

Safe to re-run: existing vaults are left as their moderators set them, and
the default list is only set when the site doesn't have one yet (change it
later with set_defaults() below or the admin tools).
"""

import os

from pylons import app_globals as g

from r2.lib import ai_content
from r2.lib.db import queries
from r2.models import Account, NotFound, Vault
from r2.models.vault import LocalizedDefaultVaults

ANY = ai_content.POLICY_ANY
NO_GEN = ai_content.POLICY_NO_GENERATED
AI_ONLY = ai_content.POLICY_AI_ONLY

# (name, title, description, AI policy, front page default)
VAULTS = [
    # technology
    ("technology", "Technology", "News and discussion about technology.", ANY, True),
    ("programming", "Programming", "Code, languages, tools and the craft of programming.", ANY, True),
    ("linux", "Linux", "Linux, its distributions and the software around it.", ANY, True),
    ("selfhosted", "Self-hosted", "Running your own services instead of renting them.", ANY, True),
    ("homelab", "Homelab", "Servers, networks and racks at home.", ANY, True),
    ("electronics", "Electronics", "Circuits, components, repairs and projects.", NO_GEN, True),
    # science
    ("science", "Science", "Research, discoveries and how the world works.", NO_GEN, True),
    ("space", "Space", "Astronomy, spaceflight and everything off-planet.", ANY, True),
    # making things
    ("diy", "DIY", "Things you built, fixed or improved yourself.", NO_GEN, True),
    ("3dprinting", "3D Printing", "Printers, prints, models and troubleshooting.", NO_GEN, True),
    # games
    ("gaming", "Gaming", "Video games of every kind.", ANY, True),
    ("retrogaming", "Retro Gaming", "Classic consoles, computers and games.", ANY, True),
    # creative (human-made; AI-generated work has its own vaults)
    ("art", "Art", "Art made by people. AI-generated art goes in /v/aiart.", NO_GEN, True),
    ("music", "Music", "Music made by people. AI-generated music goes in /v/aimusic.", NO_GEN, True),
    ("photography", "Photography", "Photos and the craft of taking them.", NO_GEN, True),
    ("writing", "Writing", "Stories, poems and writing about writing.", NO_GEN, True),
    ("aiart", "AI Art", "Art made with AI image tools.", AI_ONLY, False),
    ("aimusic", "AI Music", "Music made with AI tools.", AI_ONLY, False),
    # everything else
    ("books", "Books", "Reading, recommendations and discussion.", ANY, True),
    ("movies", "Movies", "Films, old and new.", ANY, True),
    ("food", "Food", "Cooking, recipes and things worth eating.", ANY, True),
    ("pics", "Pics", "Pictures worth sharing.", NO_GEN, True),
    ("funny", "Funny", "Things that made you laugh.", ANY, True),
    ("aww", "Aww", "Cute animals and other things that make you smile.", NO_GEN, True),
    ("til", "Today I Learned", "Interesting facts you just found out, with a source.", ANY, True),
    ("asktippr", "Ask Tippr", "Ask the community a question.", ANY, True),
    ("tippr", "Tippr", "News, feedback and questions about the site itself.", ANY, True),
    # exist, but not on the default front page
    ("news", "News", "News from around the world.", ANY, False),
    ("worldnews", "World News", "International news.", ANY, False),
    ("politics", "Politics", "Political news and discussion.", ANY, False),
]


def owner_account():
    """The admin account that creates and moderates the starter vaults."""
    names = [os.environ.get("TIPPR_ADMIN_USER")] + list(g.admins or [])
    names.append(g.system_user)
    for name in names:
        if not name:
            continue
        try:
            return Account._by_name(name)
        except NotFound:
            continue
    raise SystemExit("no admin account found; run create_default_user.py first")


def ensure_vault(owner, name, title, description, policy):
    try:
        vault = Vault._by_name(name)
    except NotFound:
        pass
    else:
        print(f"  /v/{name} exists, leaving it as is")
        return vault

    vault = Vault._new(
        name=name,
        title=title,
        author_id=owner._id,
        ip="127.0.0.1",
        lang=g.lang,
        type="public",
        link_type="any",
        public_description=description,
        ai_policy=policy,
    )
    vault._commit()
    vault.add_subscriber(owner)
    vault.add_moderator(owner)
    vault.add_contributor(owner)
    queries.new_Vault(vault)
    vault.update_search_index()
    print(f"  created /v/{name} ({policy})")
    return vault


def set_defaults(vaults):
    LocalizedDefaultVaults.set_global_vaults(vaults)
    print("front page defaults: " + ", ".join(v.name for v in vaults))


owner = owner_account()
print(f"Starter vaults (owner: {owner.name}):")
vaults = {}
for name, title, description, policy, is_default in VAULTS:
    vaults[name] = ensure_vault(owner, name, title, description, policy)

if LocalizedDefaultVaults.get_global_defaults():
    print("front page defaults are already set; not changing them")
else:
    set_defaults([vaults[name] for name, _, _, _, is_default in VAULTS
                  if is_default])

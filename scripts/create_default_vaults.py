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

"""Create the starter vaults and make the front page defaults.

Run with tippr-run (install/tippr.sh does this on every install):

    tippr-run scripts/create_default_vaults.py

The defaults lean toward technology, science, making things and fun. News
and politics vaults exist but aren't defaults, so they don't fill the front
page unless people subscribe. Creative vaults take human-made and AI-assisted
posts, with separate vaults for AI-generated art and music.

Safe to re-run: existing vaults are left as their moderators set them. The
default list is set when the site doesn't have one yet; after that, a run
adds only the defaults new to this list since the last run (r2.lib.
starter_content remembers what was offered), so a default an admin took
off stays off. To replace an existing site's defaults with this list:

    TIPPR_RESET_DEFAULTS=1 tippr-run scripts/create_default_vaults.py
"""

import os

from pylons import app_globals as g

from r2.lib import ai_content, starter_content, vault_admin
from r2.lib.db import queries
from r2.models import Account, NotFound, Vault
from r2.models.vault import LocalizedDefaultVaults

ANY = ai_content.POLICY_ANY
NO_GEN = ai_content.POLICY_NO_GENERATED
AI_ONLY = ai_content.POLICY_AI_ONLY

# (name, title, description, AI policy, front page default)
#
# Only vaults with feeds in starter_feeds.txt are front page defaults: on a
# new site the posts come from feeds, so a default without any would only
# add an empty vault to every newcomer's front page. (On a site whose
# defaults are already set, scripts/prune_default_vaults.py takes the ones
# without feeds off.)
VAULTS = [
    # tech & geek core
    ("technology", "Technology", "News and discussion about technology.", ANY, True),
    ("programming", "Programming", "Code, languages, tools and the craft of programming.", ANY, True),
    ("linux", "Linux", "Linux, its distributions and the software around it.", ANY, True),
    ("selfhosted", "Self-hosted", "Homelabs, self-hosting services, and digital sovereignty.", ANY, True),
    ("electronics", "Electronics", "Circuits, components, repairs, and hardware projects.", NO_GEN, True),
    ("mechanicalkeyboards", "Mechanical Keyboards", "Switches, keycaps, and custom keyboard builds.", NO_GEN, True),
    ("privacy", "Privacy", "Digital rights, encryption, and navigating the panopticon.", ANY, True),
    ("cybersecurity", "Cybersecurity", "Security news, breaches, vulnerabilities, and defending your systems.", ANY, True),
    ("devops", "DevOps", "Cloud, containers, infrastructure and keeping services running.", ANY, False),
    ("ainews", "AI News", "News and research about artificial intelligence.", ANY, False),
    ("gis", "GIS & Maps", "Maps, geospatial data, remote sensing and Earth observation.", ANY, False),
    
    # science & space
    ("science", "Science", "Research, discoveries and how the world works.", NO_GEN, True),
    ("space", "Space", "Astronomy, spaceflight and everything off-planet.", ANY, True),
    
    # digital entertainment
    ("gaming", "Gaming", "Video games of every kind.", ANY, True),
    ("cozygaming", "Cozy Gaming", "Relaxing games, farming sims, and low-stress gaming.", ANY, True),
    ("retrogaming", "Retro Gaming", "Classic consoles, emulation, and arcade history.", ANY, True),
    ("anime", "Anime & Manga", "Series, webtoons, fan art, and community discussion.", ANY, True),
    
    # physical making & lifestyle
    ("diy", "DIY & Making", "Things you built, fixed, or machined yourself.", NO_GEN, True),
    ("fiberarts", "Fiber Arts", "Crochet, knitting, sewing, and textile crafts.", NO_GEN, True),
    ("thrift", "Thrift & Upcycling", "Second-hand finds, vintage fashion, and sustainable flips.", NO_GEN, True),
    ("3dprinting", "3D Printing", "Printers, prints, models and troubleshooting.", NO_GEN, True),
    ("food", "Food & Baking", "Cooking, recipes, and culinary experiments.", ANY, True),
    
    # human-made creative hubs
    ("art", "Art", "Art made by people. AI art goes in /v/aiart.", NO_GEN, True),
    ("music", "Music", "Music made by people. AI music goes in /v/aimusic.", NO_GEN, True),
    ("photography", "Photography", "Photos and the craft of taking them.", NO_GEN, True),
    ("writing", "Writing", "Stories, poems, and the written word.", NO_GEN, True),
    
    # internet culture & aesthetics
    ("memes", "Memes", "Shitposts, templates, and internet lore.", ANY, True),
    ("comics", "Comics", "Webcomics, comic strips, and the people who make them.", NO_GEN, True),
    ("design", "Design", "Graphic, product and interior design, architecture and visual craft.", NO_GEN, False),
    ("curated", "Curated", "The best of the web: collections of remarkable pictures and finds.", ANY, False),
    ("blogs", "Blogs", "Independent weblogs, essays, and long reads.", NO_GEN, False),
    ("aesthetics", "Aesthetics", "Liminal spaces, visual moods, and subculture curation.", NO_GEN, True),
    ("popculture", "Pop Culture", "Fandoms, internet drama, and modern media trends.", ANY, True),
    ("pics", "Pics", "Pictures worth sharing.", NO_GEN, True),
    ("aww", "Aww", "Cute animals and wholesome content.", NO_GEN, True),
    
    # discussion & communities
    ("books", "Books", "Reading, recommendations, and literary discussion.", ANY, True),
    ("movies", "Movies & TV", "Films and television, old and new.", ANY, True),
    ("til", "Today I Learned", "Interesting facts with verified sources.", ANY, True),
    ("asktippr", "Ask Tippr", "Ask the community a question.", ANY, False),
    ("lgbtq", "LGBTQ+", "A welcoming place for LGBTQ+ people and allies.", ANY, True),
    ("skincare", "Skincare & Wellness", "Routine advice, self-care, and mental well-being.", ANY, True),

    # ai designated zones (not default)
    ("aiart", "AI Art", "Art made with AI image tools.", AI_ONLY, False),
    ("aimusic", "AI Music", "Music made with AI tools.", AI_ONLY, False),
    
    # sitewide meta & heavy news (not default)
    ("tippr", "Tippr Meta", "News, feedback, and questions about the site.", ANY, False),
    ("dragrace", "Drag Race", "Drag culture, episodes, and looks.", ANY, False),
    ("news", "News", "News from around the world.", ANY, False),
    ("worldnews", "World News", "International news.", ANY, False),
    ("politics", "Politics", "Political news and discussion.", ANY, False),
    ("business", "Business", "Markets, companies, the economy and personal finance.", ANY, False),
    ("marketing", "Marketing", "Marketing, SEO and social media.", ANY, False),
    ("sports", "Sports", "Sports news, results and discussion.", ANY, False),
    ("podcasts", "Podcasts", "New episodes and podcast recommendations.", ANY, False),
    ("videos", "Videos", "Videos worth watching: science, tech, explainers and more.", ANY, False),
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

starter_defaults = [name for name, _, _, _, is_default in VAULTS
                    if is_default]
current = LocalizedDefaultVaults.get_global_defaults()
offered = starter_content.offered_defaults()
if not current or os.environ.get("TIPPR_RESET_DEFAULTS") == "1":
    set_defaults([vaults[name] for name in starter_defaults])
    starter_content.record_defaults(starter_defaults, new_site=not current)
elif offered is None:
    # a site from before starter defaults were remembered: its defaults
    # are the admin's choice, so only remember the list from now on
    starter_content.record_defaults(starter_defaults)
    print("front page defaults are already set; leaving them (new starter "
          "defaults in later versions will be added)")
else:
    # defaults new in this version; ones offered before and taken off by
    # an admin stay off
    new = [name for name in starter_defaults if name.lower() not in offered]
    ids = set(current)
    for name in new:
        if vaults[name]._id not in ids:
            vault_admin.set_listed(vaults[name], "default", True, owner)
            print(f"  new front page default: /v/{name}")
    starter_content.record_defaults(new)
    if not new:
        print("front page defaults: no new starter defaults (ones taken off "
              "aren't added back; TIPPR_RESET_DEFAULTS=1 resets them all)")

# the private vault "message the admins" goes to (admin_message_acct), whose
# messages become tickets in the support queue (/admin/support)
from r2.lib import support
admin_vault = support.ensure_vault()
if admin_vault:
    print(f"support vault: /v/{admin_vault.name}")

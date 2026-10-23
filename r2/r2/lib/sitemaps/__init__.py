# The contents of this file are subject to the Common Public Attribution
# License Version 1.0. (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://code.reddit.com/LICENSE. The License is based on the Mozilla Public
# License Version 1.1, but Sections 14 and 15 have been added to cover use of
# software over a computer network and provide for limited attribution for the
# Original Developer. In addition, Exhibit A has been modified to be consistent
# with Exhibit B.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is reddit.
#
# The Original Developer is the Initial Developer.  The Initial Developer of
# the Original Code is reddit Inc.
#
# All portions of the code written by reddit are Copyright (c) 2006-2015 reddit
# Inc. All Rights Reserved.
# 
# Portions created by TechIdiots LLC (Tippr) are Copyright (c) 2026
# TechIdiots LLC. All Rights Reserved.
###############################################################################

"""Sitemaps (http://www.sitemaps.org/protocol.html), so search engines find
the posts and vaults nothing links to.

  r2.lib.sitemaps.live      /sitemap.xml and /sitemaps/<name>.xml: the
                            recent sitemaps, made when asked for
  r2.lib.sitemaps.complete  every post and vault, built each day by
                            tippr-job-sitemaps when /admin/site asks for it

A sitemap holds at most 50,000 addresses, so the complete set is split
into as many as it takes, all listed in the index at /sitemap.xml.
"""

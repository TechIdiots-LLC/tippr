#!/bin/bash
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

# load configuration
RUNDIR=$(dirname $0)
source $RUNDIR/install.cfg

###############################################################################
# All done!
###############################################################################
cat <<CONCLUSION

Congratulations! tippr is now installed.

The tippr application is managed by systemd as tippr.target. To see what's
currently running, run

    systemctl list-dependencies tippr.target
    systemctl list-timers 'tippr-job-*'

Scheduled jobs are "tippr-job-*" services run by timers of the same name, and
queue processors are "tippr-consumer-<queue>@<n>" services. The number of
processors per queue is set by the files in $TIPPR_HOME/consumer-count.d;
apply a changed count with:

    sudo systemctl reload tippr-consumers

Logs go to the journal, e.g.

    journalctl -u tippr-paster -f
    journalctl -u 'tippr-consumer-vote_link_q@*' --since today

You can restart the whole stack, or a single unit, with:

    sudo tippr-restart
    sudo tippr-restart tippr-consumer-scraper_q@1

The tippr code can be shut down or started up with

    sudo tippr-stop
    sudo tippr-start

And if you think caching might be hurting you, you can flush memcache with

    tippr-flush

Log in at https://$TIPPR_DOMAIN/ as the admin account "${TIPPR_ADMIN_USER:-tippr}".
Its password, and every other generated password and secret, is kept in
${TIPPR_SECRETS_FILE:-/etc/tippr/secrets.env} (readable by root only):

    sudo grep TIPPR_ADMIN_PASSWORD ${TIPPR_SECRETS_FILE:-/etc/tippr/secrets.env}

To choose your own, re-run the installer with it set, e.g.
TIPPR_ADMIN_PASSWORD=... TIPPR_ADMIN_PASSWORD_RESET=1 (the reset flag also
changes the password of an existing admin account).

Now that the core of tippr is installed, you may want to do some additional
steps:

* Ensure that $TIPPR_DOMAIN resolves to this machine.

* To populate the database with test data, run:

    cd $TIPPR_SRC/tippr
    tippr-run scripts/inject_test_data.py -c 'inject_test_data()'

* To update or re-initialize policy wiki pages (Terms of Use, Privacy Policy, etc.):

    cd $TIPPR_SRC/tippr
    tippr-run scripts/init_policy_wiki_pages.py

* After populating the db or adding your own vaults, update the /vaults
  rankings and vault name search right away (they otherwise run on a timer):

    sudo systemctl start tippr-job-update_tipprs tippr-job-update_vault_names
CONCLUSION

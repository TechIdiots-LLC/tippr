/*  EMR Version
 *
 *  Coalesce output from multiple processed logs within interval
 *  hours --> day
 *  days --> month
 *
 *  Needs to be passed: INPUT, OUTPUT
 */

/****************************************************
 * DEFINITIONS
 ****************************************************/

-- Cleanup
rmf $OUTPUT

/****************************************************
 * COALESCE
 ****************************************************/

-- sitewide
sitewide = LOAD '$INPUT/sitewide' AS (unique_id, count:long);  -- load all input files (multiple hours)

sitewide_grouped = GROUP sitewide BY unique_id; -- (unique_id, {(unique_id, count), ...}, ...)

sitewide_coalesced = FOREACH sitewide_grouped 
                     GENERATE group, SUM(sitewide.count); -- ((unique_id, SUM(sitewide.count), ...)

STORE sitewide_coalesced INTO '$OUTPUT/sitewide';

vault_counters = LOAD '$INPUT/vault' AS (vault, unique_id, count:long);

vaults_grouped = GROUP vault_counters BY (vault, unique_id);

vaults_coalesced = FOREACH vaults_grouped
                       GENERATE group.vault, group.unique_id,
                                SUM(vault_counters.count) AS count;

STORE vaults_coalesced INTO '$OUTPUT/vault';

vaultpath = LOAD '$INPUT/vaultpath' AS (vaultpath, unique_id, count:long);

vaultpath_grouped = GROUP vaultpath BY (vaultpath, unique_id);

vaultpath_coalesced = FOREACH vaultpath_grouped
                   GENERATE group.vaultpath, group.unique_id,
                            SUM(vaultpath.count) AS count;

STORE vaultpath_coalesced INTO '$OUTPUT/vaultpath';

-- language 
lang = LOAD '$INPUT/lang' AS (lang, unique_id, count:long);

lang_grouped = GROUP lang BY (lang, unique_id);

lang_coalesced = FOREACH lang_grouped
                 GENERATE group.lang, group.unique_id,
                          SUM(lang.count) AS count;

STORE lang_coalesced INTO '$OUTPUT/lang';

-- click
click = LOAD '$INPUT/clicks' AS (fullname, unique_id, count:long);

click_grouped = GROUP click BY (fullname, unique_id);

click_coalesced = FOREACH click_grouped
                  GENERATE group.fullname, group.unique_id,
                           SUM(click.count) AS count;

STORE click_coalesced INTO '$OUTPUT/clicks';

-- clicktarget
clicktarget = LOAD '$INPUT/clicks_targeted' AS (fullname, vault, unique_id, count:long);

clicktarget_grouped = GROUP clicktarget BY (fullname, vault, unique_id);

clicktarget_coalesced = FOREACH clicktarget_grouped
                        GENERATE group.fullname, group.vault, group.unique_id,
                                 SUM(clicktarget.count) AS count;

STORE clicktarget_coalesced INTO '$OUTPUT/clicks_targeted';

-- thing
thing = LOAD '$INPUT/thing' AS (fullname, unique_id, count:long);

thing_grouped = GROUP thing BY (fullname, unique_id);

thing_coalesced = FOREACH thing_grouped
                  GENERATE group.fullname, group.unique_id,
                           SUM(thing.count) AS count;

STORE thing_coalesced INTO '$OUTPUT/thing';

-- thingtarget
thingtarget = LOAD '$INPUT/thingtarget' AS (fullname, vault, unique_id, count:long);

thingtarget_grouped = GROUP thingtarget BY (fullname, vault, unique_id);

thingtarget_coalesced = FOREACH thingtarget_grouped
                        GENERATE group.fullname, group.vault, group.unique_id,
                                 SUM(thingtarget.count) AS count;

STORE thingtarget_coalesced INTO '$OUTPUT/thingtarget';

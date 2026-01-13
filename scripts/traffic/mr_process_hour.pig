/*  EMR Version
 *
 *  Process hourly logfile
 *  for each category sitewide/subreddit/srpath/lang/clicks/clicks_targeted/thing/thingtarget
 *  generate output with entries like:
 *  category, unique_id, count (e.g. subreddit: pics, 123456, 9)
 *
 *  Needs to be passed: LOGFILE, OUTPUT
 */

/****************************************************
 * DEFINITIONS
 ****************************************************/

-- Binaries - location is specified in traffic_bootstrap.sh
DEFINE PARSE_HOUR `/home/hadoop/traffic/parse_hour`;
DEFINE DECRYPT_USERINFO `/home/hadoop/traffic/decrypt_userinfo`;
DEFINE VERIFY `/home/hadoop/traffic/verify`;

-- Pixel definitions
%default URL_USERINFO '/pixel/of_destiny.png';
%default URL_ADFRAME '/pixel/of_defenestration.png';
%default URL_PROMOTEDLINK '/pixel/of_doom.png';
%default URL_CLICK '/click';

-- Cleanup
rmf $OUTPUT

/****************************************************
 * LOAD LOGFILE 
 ****************************************************/

log_raw = LOAD '$LOGFILE' USING TextLoader() AS (line);
log_parsed = STREAM log_raw THROUGH PARSE_HOUR AS (ip, path:chararray, query, response_code, unique_id);

SPLIT log_parsed INTO
    pageviews_with_path IF path == '$URL_USERINFO',
    unverified_hits IF (path == '$URL_ADFRAME' OR
                        path == '$URL_PROMOTEDLINK' OR
                        path == '$URL_CLICK');

pageviews_encrypted = FOREACH pageviews_with_path GENERATE unique_id, query;

 /****************************************************
 * PAGEVIEWS
 ****************************************************/

pageviews = STREAM pageviews_encrypted THROUGH DECRYPT_USERINFO AS (unique_id, srpath, vault, lang, cname);

-- sitewide
sitewide_pageviews = FOREACH pageviews GENERATE unique_id;  -- (unique_id)
sitewide_hourly_uniques_grouped = GROUP sitewide_pageviews BY unique_id; -- (unique_id, {(unique_id), ...}
sitewide_hourly_uniques = FOREACH sitewide_hourly_uniques_grouped
                          GENERATE group AS unique_id, COUNT(sitewide_pageviews) AS count;  -- (unique_id, count)

STORE sitewide_hourly_uniques INTO '$OUTPUT/sitewide';

vault_pageviews_filtered = FILTER pageviews 
                               BY vault IS NOT NULL;  -- exclude entries without vault
vault_pageviews_raw = FOREACH vault_pageviews_filtered 
                          GENERATE vault, unique_id;  -- limit to (vault, unique_id)
vault_hourly_uniques_grouped = GROUP vault_pageviews_raw
                                   BY (vault, unique_id); -- (vault, unique_id, {(vault, unique_id), ...})
vault_hourly_uniques = FOREACH vault_hourly_uniques_grouped
                           GENERATE group.vault, group.unique_id,
                                    COUNT(vault_pageviews_raw) AS count; -- (vault, unique_id, count)

STORE vault_hourly_uniques INTO '$OUTPUT/vault';

vaultpath_filtered = FILTER pageviews BY srpath IS NOT NULL;
vaultpath_pageviews = FOREACH vaultpath_filtered
                   GENERATE srpath AS vaultpath, unique_id;
vaultpath_hourly_uniques_grouped = GROUP vaultpath_pageviews
                                BY (vaultpath, unique_id);
vaultpath_hourly_uniques = FOREACH vaultpath_hourly_uniques_grouped
                        GENERATE group.vaultpath, group.unique_id,
                                 COUNT(vaultpath_pageviews) AS count;

STORE vaultpath_hourly_uniques INTO '$OUTPUT/vaultpath';

-- language
lang_filtered = FILTER pageviews BY lang IS NOT NULL;
lang_pageviews = FOREACH lang_filtered GENERATE lang, unique_id;
lang_hourly_uniques_grouped = GROUP lang_pageviews BY (lang, unique_id);
lang_hourly_uniques = FOREACH lang_hourly_uniques_grouped
                      GENERATE group.lang, group.unique_id,
                               COUNT(lang_pageviews) AS count;

STORE lang_hourly_uniques INTO '$OUTPUT/lang';
 
 /****************************************************
 * HITS 
 ****************************************************/

-- process unverified hits
verified = STREAM unverified_hits THROUGH VERIFY AS (unique_id, path:chararray, fullname, vault);

-- ads and promoted links

SPLIT verified INTO
    clicks_raw IF path == '$URL_CLICK',
    ad_impressions IF (path == '$URL_ADFRAME' OR
                       path == '$URL_PROMOTEDLINK');

-- clicks
clicks = FOREACH clicks_raw GENERATE fullname, unique_id;
clicks_grouped = GROUP clicks BY (fullname, unique_id);
clicks_by_hour = FOREACH clicks_grouped
                 GENERATE group.fullname, group.unique_id,
                          COUNT(clicks) AS count;

STORE clicks_by_hour INTO '$OUTPUT/clicks';

-- targeted clicks
targeted_clicks = FOREACH clicks_raw GENERATE fullname, vault, unique_id;
targeted_clicks_grouped = GROUP targeted_clicks BY (fullname, vault, unique_id);
targeted_clicks_by_hour = FOREACH targeted_clicks_grouped
                          GENERATE group.fullname, group.vault, group.unique_id,
                                   COUNT(targeted_clicks) AS count;

STORE targeted_clicks_by_hour INTO '$OUTPUT/clicks_targeted';

-- things
thing_impressions = FOREACH ad_impressions GENERATE fullname, unique_id;
thing_impressions_grouped = GROUP thing_impressions BY (fullname, unique_id);
thing_impressions_hourly = FOREACH thing_impressions_grouped
                           GENERATE group.fullname, group.unique_id,
                                    COUNT(thing_impressions) AS count;

STORE thing_impressions_hourly INTO '$OUTPUT/thing';

-- targeted things
targeted_thing_impressions = FOREACH ad_impressions 
                             GENERATE fullname, vault AS vault, unique_id;
targeted_thing_impressions_grouped = GROUP targeted_thing_impressions
                                     BY (fullname, vault, unique_id);
targeted_thing_impressions_hourly = FOREACH targeted_thing_impressions_grouped
                                    GENERATE group.fullname, group.vault,
                                             group.unique_id,
                                             COUNT(targeted_thing_impressions)
                                             AS count;

STORE targeted_thing_impressions_hourly INTO '$OUTPUT/thingtarget';

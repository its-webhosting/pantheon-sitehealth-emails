
import sqlalchemy as db

import script_context as sc


sitelens_url_count = {}


def setup_sitelens(connection) -> None:
    sc.debug('Getting SiteLens information from portal database')

    site_url_scan_config = db.Table('sites_siteurlscanconfiguration', db.MetaData(), autoload_with=connection)

    query = db.select(site_url_scan_config.c['site_id'],
                      db.func.count(db.distinct(site_url_scan_config.c['path'])).label('unique_paths_count')) \
        .where(site_url_scan_config.c['path'] != '/') \
        .group_by(site_url_scan_config.c['site_id'])

    for row in connection.execute(query).all():
        # https://github.com/sqlalchemy/sqlalchemy/discussions/10091
        # noinspection PyProtectedMember
        site = row._asdict()
        sc.debug(f'Site {site["site_id"]} has {site["unique_paths_count"]} unique paths', level=2)
        sitelens_url_count[site['site_id']] = site['unique_paths_count']


def check_sitelens_urls(site_context) -> None:
    sc.debug('Checking if SiteLens URLs have been configured')
    site_name = site_context['site']['name']
    portal_sites = sc.config['UMich']['portal']['sites']

    if site_name not in portal_sites:
        sc.console.print(f'[bold red]ERROR: Site {site_name} is not in the portal database')
        return

    portal_site_id = portal_sites[site_name]['id']
    if portal_site_id in sitelens_url_count and sitelens_url_count[portal_site_id] >= 2:
        sc.debug(f'{site_name} has {sitelens_url_count[portal_site_id]} unique SiteLens paths configured')
        return

    paths_configured = sitelens_url_count.get(portal_site_id, 0)
    sc.debug(f'[red]NOTE: {site_name} has {paths_configured} unique SiteLens paths configured')
    sc.add_news_item({
        'type': 'info',
        'csv': f'{site_name},sitelens-url-paths,{paths_configured}',
        'message': f'''
<p>To ensure accurate SiteLens reports, please
<a href="https://admin.webservices.umich.edu/sites/{portal_site_id}/scan-configurations/">configure at least two
URL paths</a>, not counting '<code>/</code>', for SiteLens to analyze on <strong>{site_name}</strong>.</p>
'''
    })

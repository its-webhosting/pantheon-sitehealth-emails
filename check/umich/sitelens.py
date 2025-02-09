
import sys
import io
import datetime

from email.utils import make_msgid

import matplotlib.pyplot as plt

import sqlalchemy as db
from rich.pretty import pprint

import script_context as sc


GAUGE_PIXELS_WIDTH = 128
GAUGE_PIXELS_HEIGHT = 128

GOOD_SCORE_MIN = 90
OK_SCORE_MIN = 50

NO_SCORE_COLOR   = '#888888'  # --rating-color-default

GOOD_SCORE_COLOR = '#00CC66'  # --rating-color-good
OK_SCORE_COLOR   = '#FFAA33'  # --rating-color-ok
BAD_SCORE_COLOR  = '#FF3333'  # --rating-color-bad

BACKGROUND_GAUGE_COLOR = '#E7F2FA'


sitelens_configured_scans_by_site = {}
sitelens_scores = {}


def setup_sitelens(connection) -> None:
    sc.debug('Getting SiteLens information from portal database')
    global sitelens_configured_scans_by_site, sitelens_scores

    site_url_scan_config = db.Table('sites_siteurlscanconfiguration', db.MetaData(), autoload_with=connection)
    sites_lighthousescanresult = db.Table('sites_lighthousescanresult', db.MetaData(), autoload_with=connection)

    # Get the configuration ids of what will be scanned for each site
    query = db.select(site_url_scan_config.c.site_id, site_url_scan_config.c.id)

    for row in connection.execute(query).all():
        # https://github.com/sqlalchemy/sqlalchemy/discussions/10091
        # noinspection PyProtectedMember
        site = row._asdict()
        if site['site_id'] not in sitelens_configured_scans_by_site:
            sitelens_configured_scans_by_site[site['site_id']] = [site['id']]
        else:
            sitelens_configured_scans_by_site[site['site_id']].append(site['id'])

    if sc.options.verbose >= 3:
        sc.console.print('SiteLens configurations by site:')
        pprint(sitelens_configured_scans_by_site)

    # Get the latest scores by running the SQL query
    #
    # SELECT configuration_id, timestamp, accessibility_score, performance_score, best_practices_score, seo_score
    # FROM sites_lighthousescanresult AS t1
    # WHERE timestamp = (
    #     SELECT MAX(timestamp) FROM sites_lighthousescanresult AS t2
    #     WHERE t1.configuration_id = t2.configuration_id
    # );
    #
    t1 = sites_lighthousescanresult.alias('t1')
    t2 = sites_lighthousescanresult.alias('t2')

    subquery = db.select(db.func.max(t2.c.timestamp)
                         ).where(t1.c.configuration_id == t2.c.configuration_id).scalar_subquery()
    query = db.select(
        t1.c.configuration_id,
        t1.c.timestamp,
        t1.c.accessibility_score,
        t1.c.performance_score,
        t1.c.best_practices_score,
        t1.c.seo_score,
    ).where(t1.c.timestamp == subquery)

    for row in connection.execute(query).all():
        # https://github.com/sqlalchemy/sqlalchemy/discussions/10091
        # noinspection PyProtectedMember
        scores = row._asdict()
        sitelens_scores[scores['configuration_id']] = scores

    sc.debug(f'Loaded {len(sitelens_scores)} SiteLens scores')


def check_sitelens_urls(site_context) -> None:
    sc.debug('Checking if SiteLens URLs have been configured')
    site_name = site_context['site']['name']
    portal_sites = sc.config['UMich']['portal']['sites']

    if site_name not in portal_sites:
        sc.console.print(f'[bold red]ERROR: Site {site_name} is not in the portal database')
        return

    portal_site_id = portal_sites[site_name]['id']
    if portal_site_id not in sitelens_configured_scans_by_site:
        sc.console.print(f'[bold red]ERROR: Site {site_name} has no SiteLens configurations, this should not happen')
        sys.exit(1)

    num_paths_configured = len(sitelens_configured_scans_by_site[portal_site_id])
    if num_paths_configured >= 4:
        sc.debug(f'[green]{site_name} has {num_paths_configured} SiteLens paths configured')
        return

    sc.debug(f'[red]NOTE: {site_name} only has {num_paths_configured} SiteLens paths configured')
    sc.add_notice({
        'type': 'info',
        'csv': f'{site_name},sitelens-url-paths,{num_paths_configured}',
        'message': f'''
<p>To ensure accurate SiteLens reports, please
<a href="https://admin.webservices.umich.edu/sites/{portal_site_id}/scan-configurations/">configure at least two
URL paths</a>, not counting '<code>/</code>', for SiteLens to analyze on <strong>{site_name}</strong>.</p>
'''
    }, site_context)


def create_gauge_image(value: int, color: str, title: str) -> bytes:
    data = [value, 100 - value]

    px = 1 / plt.rcParams['figure.dpi']  # pixel in inches
    fig, ax = plt.subplots(figsize=(GAUGE_PIXELS_WIDTH * px, GAUGE_PIXELS_HEIGHT * px), subplot_kw=dict(aspect="equal"))

    ax.pie([100], radius=1.19, wedgeprops=dict(width=1.2), colors=[BACKGROUND_GAUGE_COLOR])  # solid background color inside the gauge
    ax.pie(data, radius=1.2, wedgeprops=dict(width=0.3), counterclock=False, startangle=90, colors=[color, 'white'])

    plt.text(x=0, y=-0.1, s=f'{value}', horizontalalignment='center', verticalalignment='center', fontsize=20, weight='bold', color=color)
    ax.set_title(title, fontsize=10, weight='bold')

    l, b, w, h = ax.get_position().bounds
    ax.set_position([l, b - 0.1, w, h])  # move the gauge down a bit to balance with the title

    #plt.show()   # for tweaking or debugging
    #sys.exit(1)

    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    image = buf.read()
    buf.close()
    return image


def check_sitelens_scores(site_context) -> None:
    sc.debug('Creating section for SiteLens scores')
    site_name = site_context['site']['name']
    portal_sites = sc.config['UMich']['portal']['sites']

    if site_name not in portal_sites:
        sc.console.print(f'[bold red]ERROR: Site {site_name} is not in the portal database')
        return

    portal_site_id = portal_sites[site_name]['id']
    if portal_site_id not in sitelens_configured_scans_by_site:
        sc.console.print(f'[bold red]ERROR: Site {site_name} has no SiteLens configurations, this should not happen')
        sys.exit(1)

    paths = sitelens_configured_scans_by_site[portal_site_id]
    sc.debug(f'Checking SiteLens scores for {site_name} and paths configuration {paths}')

    score = {
        'accessibility': { 'value': 0, 'label': 'Accessibility' },
        'performance': {'value': 0, 'label': 'Performance' },
        'best_practices': {'value': 0 , 'label': 'Best Practices' },
        'seo': {'value': 0, 'label': 'SEO' },
    }
    score_ordering = ['accessibility', 'performance', 'best_practices', 'seo']

    scan_count = 0
    timestamp = datetime.datetime.min
    for path in paths:
        if path not in sitelens_scores:
            sc.console.print(f'[bold red]ERROR: SiteLens score for configuration {path} not found')
            continue
        scan_count += 1
        score['accessibility']['value'] += sitelens_scores[path]['accessibility_score']
        score['performance']['value'] += sitelens_scores[path]['performance_score']
        score['best_practices']['value'] += sitelens_scores[path]['best_practices_score']
        score['seo']['value'] += sitelens_scores[path]['seo_score']
        if sitelens_scores[path]['timestamp'] > timestamp:
            timestamp = sitelens_scores[path]['timestamp']

    if scan_count == 0:
        sc.console.print(f'[bold red]ERROR: No SiteLens scores found for {site_name}')
        return

    sitelens_date = timestamp.strftime('%Y%m%d')
    html = ''
    text = "\nSite scores:\n\n"

    for key in score_ordering:

        score[key]['value'] = int(100 * score[key]['value'] / scan_count)
        if score[key]['value'] >= GOOD_SCORE_MIN:
            color = GOOD_SCORE_COLOR
        elif score[key]['value'] >= OK_SCORE_MIN:
            color = OK_SCORE_COLOR
        else:
            color = BAD_SCORE_COLOR

        image = create_gauge_image(score[key]['value'], color, score[key]['label'])
        image_cid = make_msgid(domain='webservices.umich.edu')
        site_context['attachments'].append({
            'data': image,
            'maintype': 'image',
            'subtype': 'png',
            'filename': f'pantheon_{site_name}_{key}_{sitelens_date}.png',
            'cid': image_cid,
            'disposition': 'inline',
        })

        html += f'''
<td>
  <a href="https://admin.webservices.umich.edu/sites/{portal_site_id}/site-lens/">
    <img src="cid:{image_cid[1:-1]}" alt="{score[key]['label']}: {score[key]['value']} / 100"
      height={GAUGE_PIXELS_HEIGHT} width={GAUGE_PIXELS_WIDTH} />
  </a>
</td>
'''

        text += f"{score[key]['label']:19s}: {score[key]['value']:3d} / 100\n"

    text += "\n"

    sc.debug(f'SiteLens scores for {site_name} at {timestamp}: A11Y={score["accessibility"]["value"]}, '
        f'PERF={score["performance"]["value"]}, BP={score["best_practices"]["value"]}, SEO={score["seo"]["value"]}')

    last_run = timestamp.strftime('%B %e, %Y, %I:%M %p')
    text += f'as of {last_run}.\n\n'

    site_context['sections'].append({
        'heading': 'SiteLens',
        'content': f'''
<table role="presentation" border="0" cellpadding="0" cellspacing="30">
  <tr>{html}</tr>
</table>
<p>as of {last_run}.</p>

''',
        'text': text
    })

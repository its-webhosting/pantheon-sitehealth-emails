
import sqlalchemy as db

from rich.pretty import pprint

import script_context as sc


setup_completed = False
portal_plan_info = {}


def setup_portal_db():
    global portal_plan_info, setup_completed
    sc.debug('Getting information from portal database')
    portal_sites = {}
    db_info = sc.config['UMich']['portal']['db']
    # Same URL builder and same pool settings (pool_pre_ping et al.) as the traffic database: two
    # hand-rolled builders drift.  The portal DB section has no `type` key -- it is always MySQL --
    # so supply it here rather than requiring it in the config.
    conn_str, engine_kwargs = sc.db_engine_args({**db_info, 'type': 'mysql'})
    portal_db_engine = db.create_engine(conn_str,
                                        echo=True if sc.options.verbose >= 2 else False,
                                        **engine_kwargs)

    with portal_db_engine.connect() as connection:
        metadata = db.MetaData()

        sites_site = db.Table('sites_site', metadata, autoload_with=portal_db_engine)
        query = db.select(sites_site.c['id', 'site_slug', 'owner_group', 'shortcode'])
        for row in connection.execute(query).all():
            # https://github.com/sqlalchemy/sqlalchemy/discussions/10091
            # noinspection PyProtectedMember
            site = row._asdict()
            portal_sites[site['site_slug']] = {
                'id': site['id'],
                'owner_group': site['owner_group'],
                'shortcode': site['shortcode'],
            }

        sc.config['Pantheon']['plan_sku_to_name'] = {}
        sites_pantheonplan = db.Table('sites_pantheonplan', metadata, autoload_with=portal_db_engine)
        query = db.select(sites_pantheonplan.c[
                              'portal_plan_name',
                              'pantheon_plan_sku',
                              'traffic_limits',
                              'annual_plan_customer_charge',
                              'is_active'])
        for row in connection.execute(query).all():
            # noinspection PyProtectedMember
            plan = row._asdict()
            if plan['is_active']:
                if plan['portal_plan_name'] not in portal_plan_info:
                    portal_plan_info[plan['portal_plan_name']] = {}
                portal_plan_info[plan['portal_plan_name']]['traffic_limit'] = str(plan['traffic_limits'])
                portal_plan_info[plan['portal_plan_name']]['cost'] = str(plan['annual_plan_customer_charge'])
            sc.config['Pantheon']['plan_sku_to_name'][plan['pantheon_plan_sku']] = plan['portal_plan_name']

        sc.invoke_hooks('setup.umich.portal', connection)

    portal_db_engine.dispose()

    sc.config['UMich']['portal']['sites'] = portal_sites

    if sc.options.verbose >= 2:
        pprint(portal_sites)
        pprint(portal_plan_info)
        pprint(sc.config['Pantheon']['plan_sku_to_name'])

    setup_completed = True
    return


def plan_info(plan: str, field: str):
    # Until the portal DB has been read by the setup hook, defer: the framework re-emits the
    # marker so the post-setup config pass retries this substitution against the loaded data.
    if not setup_completed:
        return sc.DEFER
    return portal_plan_info[plan][field]

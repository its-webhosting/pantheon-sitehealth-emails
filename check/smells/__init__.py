"""The wp / drush / composer "PHP code problems" notices (BLOCKMAP B48), gated by
[Check.smells].enabled, default TRUE -- these three notices rendered unconditionally, inline in
main(), before the 2026-08-07 relocation
(development/2026-08-07-smell-notice-relocation/SPEC.md).

THE PHASE IS LOAD-BEARING.  site_pre_render, not site_post_gather beside the other framework
checks, and it carries three guarantees at once (SPEC section 3.2):

  1. Ordering.  wp_smell and drush_smell are rebound IN PLACE during site_post_gather by
     check.wordpress.ocp / check.wordpress.favicon / check.umich.drupal_ua, which are
     deliberately DAG-invisible (D-i9-3) -- they cannot declare produces: ['wp_smell'] without
     a duplicate-producer fatal against the core CONTRACT registry.  A LATER phase is
     unconditionally after them, so no `mutates` edge kind is needed; a same-phase hook would
     have needed one (SPEC section 3.3, and the README TO DO this change discharged).
  2. The --only-warn gate.  main() `continue`s above the site_pre_render firing, so a
     warning-only run emits no smell rows -- exactly as the inline emission did.  Moving this
     hook to an earlier phase silently changes -notices.csv output (PD#1).
  3. Notice order.  Nothing appended to site_context["notices"] between the old inline call
     site and this phase, so the rendered info bucket is unchanged.

tests/integration/test_hook_dag.py stays green if this moves to site_post_gather; the assertion
that goes red is test_check_smells_init.py::
test_the_phase_is_site_pre_render_and_that_is_load_bearing.
"""
import script_context as sc

if sc.config.get('Check', {}).get('smells', {}).get('enabled', True) is not False:
    from .hook import emit_smell_notices
    sc.add_hook('site_pre_render', {'name': 'check.smells.hook.emit_smell_notices',
                                    'func': emit_smell_notices,
                                    'consumes': ['wp_smell', 'drush_smell', 'composer_smell'],
                                    'produces': []})
else:
    sc.console.print('[bold yellow] Skipping check.smells because it is disabled in the config')

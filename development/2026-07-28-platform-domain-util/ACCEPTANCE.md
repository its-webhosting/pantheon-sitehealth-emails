# `find-platform-domains-dns` — Acceptance evidence (Task 6)

Every command below is SPEC §13, run for real against the live Pantheon organization and
Terminus-cached credentials on this host. Output is pasted verbatim — nothing summarized,
nothing predicted. Where the spec states an expected result, a **Match / Mismatch** line
follows the command's output.

## Environment

| | |
|---|---|
| Date | 2026-07-28 (Tue Jul 28 18:24:52 EDT 2026) |
| Git commit under test | `033c809017b357004f76c8ecdf5df44131178c72` |
| OS | Linux 6.12.76-linuxkit aarch64 (Debian container) |
| Python | 3.13.14 |
| uv | 0.11.32 (aarch64-unknown-linux-musl) |
| Terminus | 4.3.2 (used only to resolve the machine token from `~/.terminus/cache/tokens/`; the script itself never shells out to `terminus`) |
| PHP | 8.4.23 — irrelevant here: this script makes no PHP/Terminus subprocess calls, unlike the main program, which the README warns is incompatible with PHP 8.4 |
| Credentials | Machine token resolved from the single file in `~/.terminus/cache/tokens/` (`markmont@umich.edu`); `$PANTHEON_MACHINE_TOKEN` was unset |
| Config | `pantheon-sitehealth-emails.toml` → symlink → `pantheon-sitehealth-emails-config/pantheon-sitehealth-emails.toml`, `[Pantheon].org_id = "23c7208e-5f2a-4388-9fc4-5c3a038ef8b9"` |

---

## 1. Full gate: ruff + pyright + the offline suite

```bash
./run-tests --fast
```

```
All checks passed!
0 errors, 0 warnings, 0 informations
============================= test session starts ==============================
platform linux -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: /workspace
configfile: pyproject.toml
testpaths: tests
plugins: syrupy-5.4.0, hypothesis-6.156.1, cov-7.1.0, playwright-0.8.0, base-url-2.1.0, anyio-4.14.1
collected 1167 items / 2 deselected / 1165 selected

tests/e2e/test_abort_e2e.py ..                                           [  0%]
tests/e2e/test_eml_headers.py .....                                      [  0%]
tests/e2e/test_golden.py ..                                              [  0%]
tests/e2e/test_golden_cdn_change.py .......                              [  1%]
tests/e2e/test_golden_drupal.py ...                                      [  1%]
tests/e2e/test_golden_nonumich.py ......                                 [  2%]
tests/e2e/test_only_warn_e2e.py ..                                       [  2%]
tests/e2e/test_recommendation_e2e.py ...                                 [  2%]
tests/e2e/test_shim_e2e.py ...                                           [  2%]
tests/e2e/test_unknown_framework_e2e.py .                                [  2%]
tests/e2e/test_zero_traffic_e2e.py .                                     [  3%]
tests/email/test_email_roundtrip.py s                                    [  3%]
tests/integration/test_abort_run.py ...................                  [  4%]
tests/integration/test_addon_updates_notice_render.py ..                 [  4%]
tests/integration/test_cachecheck_notice_render.py ....                  [  5%]
tests/integration/test_charts.py .....                                  [  5%]
tests/integration/test_check_addon_updates.py .......                    [  6%]
tests/integration/test_check_addon_updates_init.py ....                  [  6%]
tests/integration/test_check_cloudflare_cache.py ....................... [  8%]
.....                                                                    [  9%]
tests/integration/test_check_cloudflare_egress.py ..............         [ 10%]
tests/integration/test_check_cloudflare_init.py ..........               [ 11%]
tests/integration/test_check_dns.py .....                                [ 11%]
tests/integration/test_check_drupal.py .................                 [ 12%]
tests/integration/test_check_drupal_init.py ....                        [ 13%]
tests/integration/test_check_pantheon.py ..............                  [ 14%]
tests/integration/test_check_pantheon_cdn_change.py ........             [ 15%]
tests/integration/test_check_pantheon_init.py ...                        [ 15%]
tests/integration/test_check_sitelens.py .....                           [ 15%]
tests/integration/test_check_umich_annual_billing.py ........            [ 16%]
tests/integration/test_check_umich_cloudflare_cms.py .........           [ 17%]
tests/integration/test_check_umich_drupal_ua.py ..........               [ 18%]
tests/integration/test_check_umich_wp.py .............                   [ 19%]
tests/integration/test_check_wordpress.py ...................            [ 20%]
tests/integration/test_check_wordpress_init.py ....                      [ 21%]
tests/integration/test_css_inliner_encoding.py ..................        [ 22%]
tests/integration/test_db_credentials.py .                               [ 22%]
tests/integration/test_db_roundtrip.py ...                               [ 23%]
tests/integration/test_dns_notice_render.py .......                      [ 23%]
tests/integration/test_drupal_notice_render.py .....                     [ 24%]
tests/integration/test_email_config.py ........                          [ 24%]
tests/integration/test_finish_run.py ............                        [ 25%]
tests/integration/test_gather_drupal.py ................                 [ 27%]
tests/integration/test_gather_wordpress.py ..........                    [ 28%]
tests/integration/test_hook_dag.py .                                     [ 28%]
tests/integration/test_hooks_phases.py ..........                        [ 29%]
tests/integration/test_httpseam.py ....                                  [ 29%]
tests/integration/test_import_packages.py .                              [ 29%]
tests/integration/test_mail_recipients.py ....                           [ 29%]
tests/integration/test_mime_structure.py ....                            [ 30%]
tests/integration/test_notice_registration.py ...                        [ 30%]
tests/integration/test_notice_roster.py ..                               [ 30%]
tests/integration/test_open_database.py ..                               [ 30%]
tests/integration/test_pantheon_cdn_change_notice_render.py .....        [ 31%]
tests/integration/test_pantheon_notice_render.py .......                 [ 31%]
tests/integration/test_plan_flow.py ...........                          [ 32%]
tests/integration/test_plan_recommendation_notice_render.py ..           [ 32%]
tests/integration/test_plugin_aws.py .....                               [ 33%]
tests/integration/test_plugin_cloudflare.py ....                         [ 33%]
tests/integration/test_plugin_cloudflare_client.py .....                 [ 34%]
tests/integration/test_plugin_cloudflare_fqdns.py ................       [ 35%]
tests/integration/test_plugin_cloudflare_init.py ......                  [ 36%]
tests/integration/test_plugin_umich_portal.py ..                         [ 36%]
tests/integration/test_regressions.py ....                               [ 36%]
tests/integration/test_render_report.py ...                              [ 36%]
tests/integration/test_run_terminus_markup.py ...                        [ 37%]
tests/integration/test_shim_composability.py ...                        [ 37%]
tests/integration/test_smell_notice_render.py ...                        [ 37%]
tests/integration/test_sort_notices_and_subject.py ......                [ 38%]
tests/integration/test_terminus_contract.py ...........                  [ 39%]
tests/integration/test_terminus_seam.py ....                             [ 39%]
tests/integration/test_traffic_flow.py ....                              [ 39%]
tests/integration/test_umich_drupal_ua_notice_render.py .                 [ 39%]
tests/integration/test_umich_wp_notice_render.py ...                     [ 40%]
tests/integration/test_wordpress_notice_render.py .......                [ 40%]
tests/integration/test_wrappers.py .............                        [ 41%]
tests/render/test_render.py ss                                          [ 41%]
tests/unit/test_abort_reason.py .......                                 [ 42%]
tests/unit/test_add_notice_from_notice.py .......                       [ 43%]
tests/unit/test_annual_billing_notices.py ..                            [ 43%]
tests/unit/test_argparse_contract.py ................                  [ 44%]
tests/unit/test_cachecheck_consolidation.py ............................ [ 47%]
.....                                                                    [ 47%]
tests/unit/test_cachecheck_headers.py .................................. [ 50%]
...................                                                      [ 52%]
tests/unit/test_cachecheck_pages.py .................................... [ 55%]
........                                                                 [ 55%]
tests/unit/test_config_substitution.py ..............                   [ 57%]
tests/unit/test_contract_registry.py ...........                        [ 58%]
tests/unit/test_db_resilience.py .......................                [ 60%]
tests/unit/test_dns_classify.py ......................                  [ 61%]
tests/unit/test_dns_notices.py ...............                          [ 63%]
tests/unit/test_env_plugin.py ...............                           [ 64%]
tests/unit/test_find_platform_domains_dns.py ........................... [ 66%]
........................................................................ [ 72%]
.......                                                                  [ 73%]
tests/unit/test_fqdns_decision.py ........                              [ 74%]
tests/unit/test_hook_dag_validation.py .........                        [ 75%]
tests/unit/test_house_rules.py ....                                     [ 75%]
tests/unit/test_interlock.py ..................                        [ 76%]
tests/unit/test_news.py ...........                                     [ 77%]
tests/unit/test_no_primary_domain_notice.py ......                      [ 78%]
tests/unit/test_notice.py .........                                     [ 79%]
tests/unit/test_owner_facing_encoding.py ............................... [ 81%]
...............                                                         [ 83%]
tests/unit/test_pantheon_cdn_change_chain.py .............              [ 84%]
tests/unit/test_pantheon_cdn_change_detect.py .........................  [ 86%]
tests/unit/test_pantheon_cdn_change_notices.py ...................      [ 87%]
tests/unit/test_pantheon_cdn_change_pantheon.py .................       [ 89%]
tests/unit/test_php_eol_notice.py ............                          [ 90%]
tests/unit/test_plan_catalog.py ....                                    [ 90%]
tests/unit/test_plan_costs.py .......                                   [ 91%]
tests/unit/test_plan_math.py ......................                     [ 93%]
tests/unit/test_plan_over_time.py ....                                  [ 93%]
tests/unit/test_plan_recommendation_notice.py ...                       [ 93%]
tests/unit/test_property.py ...                                         [ 94%]
tests/unit/test_property_plan.py ...                                    [ 94%]
tests/unit/test_pure_functions.py .....                                 [ 94%]
tests/unit/test_registry_reset.py ..                                    [ 95%]
tests/unit/test_resume_from.py .................                        [ 96%]
tests/unit/test_run_state.py ....                                       [ 96%]
tests/unit/test_section_gating.py ...........                           [ 97%]
tests/unit/test_site_context.py .........                               [ 98%]
tests/unit/test_smell_notices.py ..........                             [ 99%]
tests/unit/test_traffic_aggregation.py ....                             [ 99%]
tests/unit/test_traffic_table_rows.py ...                               [100%]

=============================== warnings summary ===============================
tests/integration/test_check_umich_wp.py::test_oidc_active_old_version_gets_the_reinstall_warning
tests/integration/test_check_umich_wp.py::test_oidc_current_version_gets_nothing
tests/integration/test_umich_wp_notice_render.py::test_oidc_reinstall_notice_snapshot
  /workspace/check/umich/oidc_login.py:28: PendingDeprecationWarning: Function 'semver.compare' is deprecated. Deprecated since version 3.0.0.  Still under investigation, see #258. Use the respective 'semver.Version.compare' instead.
    if semver.compare(p["version"], "1.2.99") <= 0:

tests/unit/test_php_eol_notice.py: 12 warnings
  <frozen importlib._bootstrap>:530: DeprecationWarning: the load_module() method is deprecated and slated for removal in Python 3.15; use exec_module() instead

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
--------------------------- snapshot report summary ----------------------------
107 snapshots passed.
========= 1162 passed, 3 skipped, 2 deselected, 15 warnings in 36.72s ==========
Linting (ruff, campaign ratchet) ...
Type-checking (pyright, campaign ratchet) ...
```

`exit=0` (the shell's own `$?` after the wrapper). **Match**: full gate green, ruff (`select =
ALL`) and pyright both pass, offline suite is 1162 passed / 3 skipped / 2 deselected / 0 failed.

---

## 2. The new test file alone, verbose

```bash
./run-tests tests/unit/test_find_platform_domains_dns.py -v
```

```
All checks passed!
0 errors, 0 warnings, 0 informations
============================= test session starts ==============================
platform linux -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0 -- /workspace/.venv/bin/python3
hypothesis profile 'default'
rootdir: /workspace
configfile: pyproject.toml
plugins: syrupy-5.4.0, hypothesis-6.156.1, cov-7.1.0, playwright-0.8.0, base-url-2.1.0, anyio-4.14.1
collecting ... collected 106 items

tests/unit/test_find_platform_domains_dns.py::test_normalize_and_is_platform_domain PASSED [  0%]
tests/unit/test_find_platform_domains_dns.py::test_direct_hit_reports_the_custom_domain_as_the_dns_record PASSED [  1%]
tests/unit/test_find_platform_domains_dns.py::test_mid_chain_hit_reports_the_owner_of_the_hitting_record PASSED [  2%]
tests/unit/test_find_platform_domains_dns.py::test_no_cname_is_a_clean_no_hit PASSED [  3%]
tests/unit/test_find_platform_domains_dns.py::test_nxdomain_is_a_clean_no_hit PASSED [  4%]
tests/unit/test_find_platform_domains_dns.py::test_migrated_domain_is_a_no_hit PASSED [  5%]
tests/unit/test_find_platform_domains_dns.py::test_transient_error_is_indeterminate_and_retried_once PASSED [  6%]
tests/unit/test_find_platform_domains_dns.py::test_no_nameservers_is_indeterminate_and_retried_once PASSED [  7%]
tests/unit/test_find_platform_domains_dns.py::test_transient_delay_asymmetry_only_no_nameservers_sleeps PASSED [  8%]
tests/unit/test_find_platform_domains_dns.py::test_malformed_name_is_indeterminate_not_a_crash PASSED [  9%]
tests/unit/test_find_platform_domains_dns.py::test_cname_loop_is_indeterminate PASSED [ 10%]
tests/unit/test_find_platform_domains_dns.py::test_chain_longer_than_the_hop_limit_is_indeterminate PASSED [ 11%]
tests/unit/test_find_platform_domains_dns.py::test_custom_domain_that_is_itself_a_platform_domain_is_indeterminate PASSED [ 12%]
tests/unit/test_find_platform_domains_dns.py::test_resolve_converts_a_malformed_name_into_the_named_exception PASSED [ 13%]
tests/unit/test_find_platform_domains_dns.py::test_resolve_converts_a_real_idna_exception PASSED [ 14%]
tests/unit/test_find_platform_domains_dns.py::test_wire_level_struct_error_is_transient_not_a_malformed_name PASSED [ 15%]
tests/unit/test_find_platform_domains_dns.py::test_session_authenticates_once_at_construction PASSED [ 16%]
tests/unit/test_find_platform_domains_dns.py::test_get_returns_decoded_json PASSED [ 16%]
tests/unit/test_find_platform_domains_dns.py::test_401_reauthenticates_once_then_succeeds PASSED [ 17%]
tests/unit/test_find_platform_domains_dns.py::test_reauthentication_does_not_consume_the_transport_retry_budget PASSED [ 18%]
tests/unit/test_find_platform_domains_dns.py::test_401_twice_raises_session_expired_not_a_plain_api_error PASSED [ 19%]
tests/unit/test_find_platform_domains_dns.py::test_failure_to_reauthenticate_is_also_session_expired PASSED [ 20%]
tests/unit/test_find_platform_domains_dns.py::test_reauthentication_notifies_the_caller PASSED [ 21%]
tests/unit/test_find_platform_domains_dns.py::test_500_is_retried_once_then_succeeds PASSED [ 22%]
tests/unit/test_find_platform_domains_dns.py::test_500_twice_raises_named_error PASSED [ 23%]
tests/unit/test_find_platform_domains_dns.py::test_429_is_retried_like_a_5xx PASSED [ 24%]
tests/unit/test_find_platform_domains_dns.py::test_connect_error_is_retried_once_then_raises_named_error PASSED [ 25%]
tests/unit/test_find_platform_domains_dns.py::test_undecodable_body_raises_named_error PASSED [ 26%]
tests/unit/test_find_platform_domains_dns.py::test_neither_token_nor_response_body_ever_leaks_into_error_text PASSED [ 27%]
tests/unit/test_find_platform_domains_dns.py::test_machine_token_prefers_the_environment PASSED [ 28%]
tests/unit/test_find_platform_domains_dns.py::test_machine_token_reads_the_single_terminus_cache_file PASSED [ 29%]
tests/unit/test_find_platform_domains_dns.py::test_machine_token_refuses_to_guess_between_several_cache_files PASSED [ 30%]
tests/unit/test_find_platform_domains_dns.py::test_machine_token_missing_cache_directory_is_named PASSED [ 31%]
tests/unit/test_find_platform_domains_dns.py::test_machine_token_undecodable_cache_file_is_named PASSED [ 32%]
tests/unit/test_find_platform_domains_dns.py::test_machine_token_cache_file_without_a_token_key_is_named PASSED [ 33%]
tests/unit/test_find_platform_domains_dns.py::test_machine_token_cache_file_holding_a_non_object_json_value_is_named PASSED [ 33%]
tests/unit/test_find_platform_domains_dns.py::test_machine_token_empty_cache_directory_is_named PASSED [ 34%]
tests/unit/test_find_platform_domains_dns.py::test_machine_token_unreadable_cache_directory_is_named PASSED [ 35%]
tests/unit/test_find_platform_domains_dns.py::test_main_returns_2_when_the_machine_token_cache_is_unreadable PASSED [ 36%]
tests/unit/test_find_platform_domains_dns.py::test_org_sites_quotes_the_org_id_in_the_url PASSED [ 37%]
tests/unit/test_find_platform_domains_dns.py::test_org_sites_walks_every_page PASSED [ 38%]
tests/unit/test_find_platform_domains_dns.py::test_org_sites_stops_on_a_short_first_page PASSED [ 39%]
tests/unit/test_find_platform_domains_dns.py::test_org_sites_handles_an_empty_organization PASSED [ 40%]
tests/unit/test_find_platform_domains_dns.py::test_org_sites_handles_a_site_count_that_is_an_exact_multiple_of_the_page_size PASSED [ 41%]
tests/unit/test_find_platform_domains_dns.py::test_org_sites_retries_an_ignored_cursor_then_succeeds PASSED [ 42%]
tests/unit/test_find_platform_domains_dns.py::test_ignored_cursor_retry_uses_the_retry_prefix_not_skipped PASSED [ 43%]
tests/unit/test_find_platform_domains_dns.py::test_org_sites_gives_up_loudly_when_the_cursor_stays_ignored PASSED [ 44%]
tests/unit/test_find_platform_domains_dns.py::test_org_sites_caps_the_page_loop PASSED [ 45%]
tests/unit/test_find_platform_domains_dns.py::test_named_sites_resolves_each_name_and_prefers_the_canonical_name PASSED [ 46%]
tests/unit/test_find_platform_domains_dns.py::test_named_sites_percent_encodes_the_site_name PASSED [ 47%]
tests/unit/test_find_platform_domains_dns.py::test_unexpected_response_shapes_raise_the_named_error PASSED [ 48%]
tests/unit/test_find_platform_domains_dns.py::test_partition_domains_splits_custom_from_platform PASSED [ 49%]
tests/unit/test_find_platform_domains_dns.py::test_partition_domains_of_an_uninitialized_environment PASSED [ 50%]
tests/unit/test_find_platform_domains_dns.py::test_partition_domains_reports_an_unknown_type_instead_of_dropping_it PASSED [ 50%]
tests/unit/test_find_platform_domains_dns.py::test_site_environments_returns_every_environment PASSED [ 51%]
tests/unit/test_find_platform_domains_dns.py::test_clean_hit_writes_exactly_the_five_fields PASSED [ 52%]
tests/unit/test_find_platform_domains_dns.py::test_csv_uses_unix_line_endings PASSED [ 53%]
tests/unit/test_find_platform_domains_dns.py::test_indeterminate_domain_reports_and_counts_but_writes_no_row PASSED [ 54%]
tests/unit/test_find_platform_domains_dns.py::test_dead_platform_domain_warns_but_still_writes_the_row PASSED [ 55%]
tests/unit/test_find_platform_domains_dns.py::test_transient_lookup_of_the_platform_domain_does_not_warn PASSED [ 56%]
tests/unit/test_find_platform_domains_dns.py::test_cross_site_target_warns_but_still_writes_the_row PASSED [ 57%]
tests/unit/test_find_platform_domains_dns.py::test_mid_chain_hit_warns_that_the_record_is_an_alias PASSED [ 58%]
tests/unit/test_find_platform_domains_dns.py::test_direct_hit_does_not_warn_about_an_alias PASSED [ 59%]
tests/unit/test_find_platform_domains_dns.py::test_each_row_is_flushed_as_it_is_written PASSED [ 60%]
tests/unit/test_find_platform_domains_dns.py::test_verbose_reports_per_site_counts PASSED [ 61%]
tests/unit/test_find_platform_domains_dns.py::test_a_session_expiry_aborts_the_sweep_instead_of_counting_indeterminates PASSED [ 62%]
tests/unit/test_find_platform_domains_dns.py::test_a_malformed_domains_payload_is_one_environments_indeterminate PASSED [ 63%]
tests/unit/test_find_platform_domains_dns.py::test_sweep_records_where_it_stopped PASSED [ 64%]
tests/unit/test_find_platform_domains_dns.py::test_sweep_site_counts_environments_and_domains PASSED [ 65%]
tests/unit/test_find_platform_domains_dns.py::test_failed_environment_listing_counts_once_and_continues PASSED [ 66%]
tests/unit/test_find_platform_domains_dns.py::test_failed_domain_listing_counts_once_and_continues_to_the_next_environment PASSED [ 66%]
tests/unit/test_find_platform_domains_dns.py::test_sweep_env_reports_and_counts_an_unknown_domain_type PASSED [ 67%]
tests/unit/test_find_platform_domains_dns.py::test_verbose_sweep_prints_the_per_site_progress_counter PASSED [ 68%]
tests/unit/test_find_platform_domains_dns.py::test_cross_site_warning_with_no_platform_domains_reports_none_listed PASSED [ 69%]
tests/unit/test_find_platform_domains_dns.py::test_counters_summary_format PASSED [ 70%]
tests/unit/test_find_platform_domains_dns.py::test_org_id_is_read_from_the_config PASSED [ 71%]
tests/unit/test_find_platform_domains_dns.py::test_missing_org_id_raises_out_of_the_low_level_helper PASSED [ 72%]
tests/unit/test_find_platform_domains_dns.py::test_parser_rejects_abbreviations PASSED [ 73%]
tests/unit/test_find_platform_domains_dns.py::test_parser_accepts_site_arguments PASSED [ 74%]
tests/unit/test_find_platform_domains_dns.py::test_main_returns_2_when_the_config_has_no_org_id PASSED [ 75%]
tests/unit/test_find_platform_domains_dns.py::test_main_returns_2_when_the_config_is_missing PASSED [ 76%]
tests/unit/test_find_platform_domains_dns.py::test_main_returns_2_for_a_config_whose_pantheon_is_not_a_table PASSED [ 77%]
tests/unit/test_find_platform_domains_dns.py::test_main_returns_2_for_a_config_that_is_not_utf8 PASSED [ 78%]
tests/unit/test_find_platform_domains_dns.py::test_verbose_prints_the_reauthentication_note_and_quiet_does_not PASSED [ 79%]
tests/unit/test_find_platform_domains_dns.py::test_main_returns_1_when_the_sweep_had_an_indeterminate PASSED [ 80%]
tests/unit/test_find_platform_domains_dns.py::test_main_returns_0_on_a_clean_sweep PASSED [ 81%]
tests/unit/test_find_platform_domains_dns.py::test_an_abort_names_the_completed_site_and_the_unreached_ones PASSED [ 82%]
tests/unit/test_find_platform_domains_dns.py::test_ctrl_c_returns_130_and_says_where_it_stopped PASSED [ 83%]
tests/unit/test_find_platform_domains_dns.py::test_broken_pipe_returns_2_and_reports_like_every_other_abort PASSED [ 83%]
tests/unit/test_find_platform_domains_dns.py::test_broken_pipe_dup2_recipe_actually_runs PASSED [ 84%]
tests/unit/test_find_platform_domains_dns.py::test_session_expiry_returns_2_not_1 PASSED [ 85%]
tests/unit/test_find_platform_domains_dns.py::test_an_unexpected_error_returns_2_never_1 PASSED [ 86%]
tests/unit/test_find_platform_domains_dns.py::test_system_exit_mid_sweep_propagates_unconverted PASSED [ 87%]
tests/unit/test_find_platform_domains_dns.py::test_no_token_ever_reaches_stdout_or_stderr PASSED [ 88%]
tests/unit/test_find_platform_domains_dns.py::test_no_token_ever_reaches_stdout_or_stderr_at_default_verbosity PASSED [ 89%]
tests/unit/test_find_platform_domains_dns.py::test_build_session_pins_no_redirects_and_the_http_timeout PASSED [ 90%]
tests/unit/test_find_platform_domains_dns.py::test_build_session_never_constructs_a_client_when_the_token_cannot_be_resolved PASSED [ 91%]
tests/unit/test_find_platform_domains_dns.py::test_main_writes_csv_with_unix_line_endings_only PASSED [ 92%]
tests/unit/test_find_platform_domains_dns.py::test_shape_error_during_listing_returns_2_not_1 PASSED [ 93%]
tests/unit/test_find_platform_domains_dns.py::test_report_stop_says_during_when_no_site_completed_yet PASSED [ 94%]
tests/unit/test_find_platform_domains_dns.py::test_report_stop_lists_multiple_remaining_site_names_space_separated PASSED [ 95%]
tests/unit/test_find_platform_domains_dns.py::test_report_stop_says_something_sane_when_ctrl_c_lands_before_the_first_site_starts PASSED [ 96%]
tests/unit/test_find_platform_domains_dns.py::test_get_converts_invalid_url_into_a_named_error PASSED [ 97%]
tests/unit/test_find_platform_domains_dns.py::test_hostile_org_id_does_not_produce_an_unnamed_traceback PASSED [ 98%]
tests/unit/test_find_platform_domains_dns.py::test_ctrl_c_during_prepare_sweep_returns_130_cleanly PASSED [ 99%]
tests/unit/test_find_platform_domains_dns.py::test_report_stop_ignores_a_second_sigint_while_printing PASSED [100%]

============================= 106 passed in 0.91s ==============================
Linting (ruff, campaign ratchet) ...
Type-checking (pyright, campaign ratchet) ...
```

`exit=0`. **Match**: 106/106 passed, including the copied-`resolve()` cases (item 9), the
security cases (item 12), and the abort cases (item 13).

---

## 3. Help text

```bash
./find-platform-domains-dns --help
```

```
usage: find-platform-domains-dns [-h] [-c CONFIG] [-v] [SITE ...]

List Pantheon custom domains whose DNS still reaches a platform domain.

positional arguments:
  SITE                 site names to sweep; default is the whole organization

options:
  -h, --help           show this help message and exit
  -c, --config CONFIG  TOML file to read [Pantheon].org_id from
  -v, --verbose        per-site progress on stderr
```

`exit=0`.

---

## 4. Known-migrated site: `its-wws-test1`

```bash
./find-platform-domains-dns its-wws-test1; echo "exit=$?"
```

stdout:
```
(empty)
```

stderr:
```
sites=1 envs=7 custom_domains=2 rows=0 indeterminate=0
```

`exit=0`. **Match**: SPEC §13 expects "ZERO CSV rows on stdout and exit 0" for a known-migrated
site — observed. `envs=7` matches SPEC §12's note that `its-wws-test1` has 7 environments
(`autopilot, dev, live, test, test-jpr, test-mark, test-md`) and is atypical.

---

## 5. Known-legacy site: `bus-occb`

```bash
./find-platform-domains-dns bus-occb; echo "exit=$?"
```

stdout:
```
bus-occb,live,occb.bus.umich.edu,occb.bus.umich.edu,live-bus-occb.pantheonsite.io
```

stderr:
```
sites=1 envs=3 custom_domains=1 rows=1 indeterminate=0
```

`exit=0`. **Match**: byte-identical to the exact row SPEC §13 and §5 predict.

**Live cross-check of the `dns_record` column (Task 6 instruction 1)** — confirming the fourth
field really is the FQDN owning the hitting CNAME record:

```bash
dig +short occb.bus.umich.edu CNAME
```
```
live-bus-occb.pantheonsite.io.
```

```bash
dig +short live-bus-occb.pantheonsite.io CNAME
```
```
fe4.edge.pantheon.io.
```

`dig` confirms `occb.bus.umich.edu` itself carries the CNAME to `live-bus-occb.pantheonsite.io`
— a **direct hit**, so `dns_record == custom_domain` is correct here (SPEC §6.3/§5 example 1).

**Gap, stated rather than papered over.** This is the only row Task 6's sanctioned live sites
produce. All three sanctioned sites (`its-wws-test1`, `its-wws-test2`, `bus-occb`) were swept
(the third is not one of SPEC §13's named commands, but is a sanctioned read-only site used
here only to widen this specific check — see command 5a below); none produced a mid-chain hit
(`dns_record != custom_domain`). **The mid-chain-vs-direct distinction in the `dns_record`
column could not be cross-checked against real DNS with the sites this task is sanctioned to
use.** It is covered by unit tests only
(`test_mid_chain_hit_reports_the_owner_of_the_hitting_record`,
`test_mid_chain_hit_warns_that_the_record_is_an_alias`, both green in command 2 above). A live
mid-chain example would require a full-organization sweep or a site outside the sanctioned set,
neither of which this task authorizes.

### 5a. Supplementary (not a §13 command): `its-wws-test2`

Run only to widen the search for a live mid-chain example, using the other sanctioned
read-only test site:

```bash
./find-platform-domains-dns its-wws-test2; echo "exit=$?"
```

stdout: `(empty)`. stderr:
```
sites=1 envs=5 custom_domains=3 rows=0 indeterminate=0
```

`exit=0`. Zero rows — does not resolve the gap noted above.

---

## 6. Clean-file behavior

```bash
./find-platform-domains-dns its-wws-test1 bus-occb > /tmp/pd.csv 2>/tmp/pd.err
echo "exit=$?"; cat /tmp/pd.csv; cat /tmp/pd.err
```

```
exit=0
bus-occb,live,occb.bus.umich.edu,occb.bus.umich.edu,live-bus-occb.pantheonsite.io
sites=2 envs=10 custom_domains=3 rows=1 indeterminate=0
```

**Match**: `/tmp/pd.csv` contains exactly one line, the `bus-occb` row, nothing else; all
diagnostics landed in `/tmp/pd.err`.

**CSV-purity verification (Task 6 instruction 2).** Byte-level check of `/tmp/pd.csv`:

```bash
grep -c $'\r' /tmp/pd.csv
```
```
0
```
(no match — `grep -c` returned nonzero exit for zero matches)

```bash
od -c /tmp/pd.csv | tail -5
```
```
0000040   ,   o   c   c   b   .   b   u   s   .   u   m   i   c   h   .
0000060   e   d   u   ,   l   i   v   e   -   b   u   s   -   o   c   c
0000100   b   .   p   a   n   t   h   e   o   n   s   i   t   e   .   i
0000120   o  \n
0000122
```

Confirmed: the file ends in a bare `\n`, no `\r` anywhere, and no line beyond the single CSV
row — `/tmp/pd.csv` is CSV and nothing else.

---

## 7. Fatal path: config with no `[Pantheon].org_id`

```bash
./find-platform-domains-dns -c /dev/null; echo "exit=$?"
```

```
ERROR: /dev/null has no usable [Pantheon].org_id (KeyError('Pantheon'))
exit=2
```

**Match**: named message (identifies the exact cause, `KeyError('Pantheon')`), exit 2, no
traceback.

---

## 8. Broken pipe (G16)

```bash
./find-platform-domains-dns bus-occb | head -0; echo "exit=${PIPESTATUS[0]}"
```

```
ERROR: sweep did not complete (stdout closed (broken pipe))
sites=1 envs=2 custom_domains=1 rows=0 indeterminate=0
Stopped during bus-occb.
1 site not reached. Resume with:
  find-platform-domains-dns bus-occb
exit=2
```

**Match**: named `ERROR: sweep did not complete (stdout closed (broken pipe))` message, the
`§7.3` abort report (`Stopped during bus-occb.` — the only site had not yet completed when the
pipe closed — plus the paste-able re-run command), exit 2, **no Python traceback**.

Re-run with stdout/stderr captured to separate files to confirm the split held even under the
broken-pipe path:

```bash
./find-platform-domains-dns bus-occb 2>/tmp/cmd8.err | head -0 >/tmp/cmd8.out
echo "exit=${PIPESTATUS[0]}"
```
```
exit=2
```
stdout (`/tmp/cmd8.out`): 0 bytes (confirmed via `wc -c`). stderr (`/tmp/cmd8.err`):
```
ERROR: sweep did not complete (stdout closed (broken pipe))
sites=1 envs=2 custom_domains=1 rows=0 indeterminate=0
Stopped during bus-occb.
1 site not reached. Resume with:
  find-platform-domains-dns bus-occb
```

Note: `envs=2` here vs. `envs=3` in command 5's clean run is expected, real variance — `head
-0` closes the pipe as soon as it connects, so the exact environment the sweep was mid-processing
when `BrokenPipeError` fired differs run to run. It is not a defect; SPEC §7.3 requires the
count/position to reflect wherever the sweep actually was, not a fixed number.

Exit code stayed at 2, not 120 — confirming the `os.dup2`-onto-devnull recipe G16 documents (to
suppress CPython's shutdown re-flush of the closed stdout) is actually working, not merely
present in the diff (PD#14: an untriggered defensive line is an unverified instrument).

---

## SPEC §15 closing-audit questions

Per the task brief: every question in SPEC §15 needs a full-organization sweep (~38 minutes),
which is explicitly **not** an acceptance step (§13's closing line: "A full-organization sweep
is NOT an acceptance step... Run it when you actually want the list") and was not run for this
task. Recorded below, by number, checked against SPEC §15 as written:

1. **Q1** (mid-chain/duplicate-`dns_record` question — how many rows had `dns_record !=
   custom_domain`, and did any `dns_record` repeat across rows) — open, needs a full sweep.
2. **Q2** (total rows and indeterminates on the first full sweep, and whether indeterminates
   are systematic) — open, needs a full sweep.
3. **Q3** (did G13 cross-site targets fire, and were they safe to hand to the downstream
   rewriter) — open, needs a full sweep.
4. **Q4** (uninitialized-environment question — did any custom domain turn out attached to an
   `initialized: false` environment) — open, needs a full sweep.
5. **Q5** (did the G4a ignored-cursor detector fire during a real full sweep) — open, needs a
   full sweep.
6. **Q6** (short-non-final-page question — did the pagination loop ever see a page that was
   neither 100 nor final) — open, needs a full sweep.

---

## Summary

All eight SPEC §13 commands were run for real, on live Pantheon and live DNS, and matched their
predicted results exactly:

| # | Command | Result |
|---|---|---|
| 1 | `./run-tests --fast` | Match — green |
| 2 | `./run-tests tests/unit/test_find_platform_domains_dns.py -v` | Match — 106/106 |
| 3 | `--help` | ran, help text as shown |
| 4 | `its-wws-test1` | Match — 0 rows, exit 0 |
| 5 | `bus-occb` | Match — the predicted row, byte-identical; `dns_record` cross-checked live with `dig` |
| 6 | `its-wws-test1 bus-occb > file` | Match — clean CSV file, all diagnostics on stderr, no `\r` |
| 7 | `-c /dev/null` | Match — named fatal message, exit 2 |
| 8 | `bus-occb \| head -0` | Match — named message, §7.3 abort report, exit 2, no traceback |

**Gap, named rather than hidden**: no live mid-chain hit (`dns_record != custom_domain`) exists
among the sanctioned test sites, so the `dns_record` column's mid-chain behavior is verified
only by unit test, not against real DNS. A full-organization sweep (out of scope for Task 6)
would very likely surface one, per SPEC §12's sampled rate of non-zero-but-rare mid-chain hits.

---

## Re-verification after the whole-branch review fix wave (2026-07-28)

The fix wave changed `main()` (a G0 closed-stream gate, the `report_stop` stdout-detach, the
config read moved onto the org-only path, and a resume command rebuilt from argv), so SPEC §13's
commands were re-run rather than assumed to still hold. Verbatim output.

```
$ ./run-tests --fast
... 1185 passed, 3 skipped, 2 deselected, 15 warnings in 32.64s
(ruff, campaign ratchet — passed; pyright, campaign ratchet — passed; both gate before pytest)

$ ./find-platform-domains-dns --help
usage: find-platform-domains-dns [-h] [-c CONFIG] [-v] [SITE ...]

List Pantheon custom domains whose DNS still reaches a platform domain.

positional arguments:
  SITE                 site names to sweep; default is the whole organization

options:
  -h, --help           show this help message and exit
  -c, --config CONFIG  TOML file to read [Pantheon].org_id from; whole-
                       organization sweeps only, a SITE sweep never reads it
  -v, --verbose        per-site progress on stderr

$ ./find-platform-domains-dns its-wws-test1; echo "exit=$?"
sites=1 envs=7 custom_domains=2 rows=0 indeterminate=0
exit=0

$ ./find-platform-domains-dns bus-occb; echo "exit=$?"
bus-occb,live,occb.bus.umich.edu,occb.bus.umich.edu,live-bus-occb.pantheonsite.io
sites=1 envs=3 custom_domains=1 rows=1 indeterminate=0
exit=0

$ ./find-platform-domains-dns -c /dev/null; echo "exit=$?"
ERROR: /dev/null has no usable [Pantheon].org_id (KeyError('Pantheon'))
exit=2

$ ./find-platform-domains-dns bus-occb | head -0; echo "exit=${PIPESTATUS[0]}"
ERROR: sweep did not complete (stdout closed (broken pipe))
sites=1 envs=2 custom_domains=1 rows=0 indeterminate=0
Stopped during bus-occb.
1 site not reached. Resume with:
  find-platform-domains-dns bus-occb
exit=2
```

### The four live reproductions the fix wave closed

Each was measured before the fix and re-measured after it. Before/after, verbatim.

**C1 — a non-string `[Pantheon].org_id`.**

```
BEFORE
$ printf '[Pantheon]\norg_id = 12345\n' > /tmp/bad1.toml
$ ./find-platform-domains-dns -c /tmp/bad1.toml; echo "exit=$?"
Traceback (most recent call last):
  ...
  File "/workspace/./find-platform-domains-dns", line 449, in org_sites
    path = f"/organizations/{quote(org_id, safe='')}/memberships/sites?limit={PAGE_LIMIT}"
TypeError: quote_from_bytes() expected bytes
exit=1

AFTER
$ ./find-platform-domains-dns -c /tmp/bad1.toml; echo "exit=$?"
ERROR: /tmp/bad1.toml has no usable [Pantheon].org_id (TypeError('[Pantheon].org_id should be a string, got int'))
exit=2
$ printf '[Pantheon]\norg_id = ["a"]\n' > /tmp/bad2.toml
$ ./find-platform-domains-dns -c /tmp/bad2.toml; echo "exit=$?"
ERROR: /tmp/bad2.toml has no usable [Pantheon].org_id (TypeError('[Pantheon].org_id should be a string, got list'))
exit=2
```

**I1 — exit 120 from the interpreter's shutdown flush, on any stdout failure that is not a pipe.**

```
BEFORE
$ ./find-platform-domains-dns bus-occb > /dev/full; echo "exit=$?"
ERROR: sweep did not complete (unexpected OSError: [Errno 28] No space left on device)
sites=1 envs=2 custom_domains=1 rows=0 indeterminate=0
Stopped during bus-occb.
1 site not reached. Resume with:
  find-platform-domains-dns bus-occb
Exception ignored on flushing sys.stdout:
OSError: [Errno 28] No space left on device
exit=120

AFTER
$ ./find-platform-domains-dns bus-occb > /dev/full; echo "exit=$?"
ERROR: sweep did not complete (unexpected OSError: [Errno 28] No space left on device)
sites=1 envs=2 custom_domains=1 rows=0 indeterminate=0
Stopped during bus-occb.
1 site not reached. Resume with:
  find-platform-domains-dns bus-occb
exit=2
```

**I2 — a closed stdout, and (worse) a closed stderr silently polluting the CSV.**

```
BEFORE
$ ./find-platform-domains-dns bus-occb >&-
Traceback (most recent call last):
  ...
  File "/workspace/./find-platform-domains-dns", line 762, in main
    sweeper = Sweeper(session.get, csv.writer(sys.stdout, lineterminator="\n"), sys.stdout,
TypeError: argument 1 must have a "write" method
exit=1

$ ./find-platform-domains-dns its-wws-test1 2>&- > /tmp/o.out; echo $?
0
$ cat /tmp/o.out
sites=1 envs=7 custom_domains=2 rows=0 indeterminate=0      <-- a summary line inside the CSV

AFTER
$ ./find-platform-domains-dns its-wws-test1 >&- ; echo "exit=$?"
ERROR: standard output is closed; there is nowhere to write the CSV
exit=2
$ ./find-platform-domains-dns its-wws-test1 2>&- > /tmp/o.out; echo "exit=$?"
exit=2
$ cat /tmp/o.out
ERROR: standard error is closed; every operator message would land in the CSV on stdout
```

**m1 / m2 — the config gate on a path that does not consume it, and a resume command that
dropped every flag.**

```
BEFORE
$ cd /tmp && /workspace/find-platform-domains-dns its-wws-test1; echo "exit=$?"
ERROR: could not read pantheon-sitehealth-emails.toml: [Errno 2] No such file or directory: 'pantheon-sitehealth-emails.toml'
exit=2

AFTER
$ cd /tmp && /workspace/find-platform-domains-dns its-wws-test1; echo "exit=$?"
sites=1 envs=7 custom_domains=2 rows=0 indeterminate=0
exit=0

AFTER (m2: the resume command now carries -v and -c)
$ ./find-platform-domains-dns -v -c pantheon-sitehealth-emails.toml bus-occb its-wws-test1 | head -0
[1/2] bus-occb
ERROR: sweep did not complete (stdout closed (broken pipe))
sites=1 envs=2 custom_domains=1 rows=0 indeterminate=0
Stopped during bus-occb.
2 sites not reached. Resume with:
  find-platform-domains-dns -v -c pantheon-sitehealth-emails.toml bus-occb its-wws-test1
exit=2
```
---

## Re-verification after the residual fix wave (2026-07-28)

The residual wave changed `main()` again (the summary print moved inside the try, an `OSError`
arm on the startup handler, every abort-report line routed through `report_line()`, and
`resume_command()` switched to a membership test), so SPEC §13 items 4, 5 and 8 were re-run
rather than assumed to still hold. Verbatim output — no regression.

```
$ ./find-platform-domains-dns its-wws-test1; echo "exit=$?"
sites=1 envs=7 custom_domains=2 rows=0 indeterminate=0
exit=0

$ ./find-platform-domains-dns bus-occb; echo "exit=$?"
bus-occb,live,occb.bus.umich.edu,occb.bus.umich.edu,live-bus-occb.pantheonsite.io
sites=1 envs=3 custom_domains=1 rows=1 indeterminate=0
exit=0

$ ./find-platform-domains-dns bus-occb | head -0; echo "exit=${PIPESTATUS[0]}"
ERROR: sweep did not complete (stdout closed (broken pipe))
sites=1 envs=2 custom_domains=1 rows=0 indeterminate=0
Stopped during bus-occb.
1 site not reached. Resume with:
  find-platform-domains-dns bus-occb
exit=2

$ ./run-tests --fast
All checks passed!                        (ruff, campaign ratchet)
0 errors, 0 warnings, 0 informations      (pyright, campaign ratchet)
... 1194 passed, 3 skipped, 2 deselected, 15 warnings in 29.70s
```

### The live reproductions the residual wave closed

**Finding 1 (G19) — a stderr write failure left the §7 exit-code taxonomy.** Four commands,
before and after. Every "before" exited **120**, which no `case $?` over 0/1/2/130 catches.

```
BEFORE
$ ./find-platform-domains-dns bus-occb 2> /dev/full > /tmp/o3.out; echo "exit=$?"
exit=120
$ cat /tmp/o3.out
bus-occb,live,occb.bus.umich.edu,occb.bus.umich.edu,live-bus-occb.pantheonsite.io
                                    <-- a COMPLETE CSV, reported with a code outside the taxonomy

$ ./find-platform-domains-dns -v bus-occb 2> /dev/full > /tmp/o4.out; echo "exit=$?"
exit=120
$ wc -c < /tmp/o4.out
0                                   <-- EMPTY: the sweep died at its first _progress() write and
                                        nothing, anywhere, said so

$ ./find-platform-domains-dns -c /dev/null 2> /dev/full; echo "exit=$?"
exit=120                            <-- report_startup_failure()'s own print, before any sweep

$ ./find-platform-domains-dns its-wws-test1 2>&- > /dev/full; echo "exit=$?"
exit=120                            <-- G0 reporting a closed stderr onto a full stdout

AFTER
$ ./find-platform-domains-dns bus-occb 2> /dev/full > /tmp/o3.out; echo "exit=$?"
exit=2
$ cat /tmp/o3.out
bus-occb,live,occb.bus.umich.edu,occb.bus.umich.edu,live-bus-occb.pantheonsite.io

$ ./find-platform-domains-dns -v bus-occb 2> /dev/full > /tmp/o4.out; echo "exit=$?"
exit=2

$ ./find-platform-domains-dns -c /dev/null 2> /dev/full; echo "exit=$?"
exit=2

$ ./find-platform-domains-dns its-wws-test1 2>&- > /dev/full; echo "exit=$?"
exit=2
```

The `-v` run still writes no CSV, and that is deliberate (SPEC §7's G19 detail): the sweep really
does stop at its first progress line, because continuing with the operator's output going
silently nowhere is what PD#1 forbids. What changed is that the stop is now **loud and inside
the taxonomy** rather than an exit code nothing documents.

**Finding 2 — `resume_command()` mangled a short-option bundle and dropped the site list.**

```
BEFORE (in-process, against the loaded module)
>>> argv = ['-vc', 'prod.toml', 's1', 's2']
>>> build_arg_parser().parse_args(argv)
Namespace(config='prod.toml', verbose=True, site=['s1', 's2'])
>>> resume_command(argv, ['s2'])
'find-platform-domains-dns -vc s2'
>>> build_arg_parser().parse_args(['-vc', 's2'])          # what the operator would paste
Namespace(config='s2', verbose=True, site=[])             # whole-ORG sweep, config named 's2'

AFTER (live, through the real abort report)
$ ./find-platform-domains-dns -vc pantheon-sitehealth-emails.toml bus-occb its-wws-test1 | head -0
[1/2] bus-occb
ERROR: sweep did not complete (stdout closed (broken pipe))
sites=1 envs=2 custom_domains=1 rows=0 indeterminate=0
Stopped during bus-occb.
2 sites not reached. Resume with:
  find-platform-domains-dns -vc pantheon-sitehealth-emails.toml bus-occb its-wws-test1
exit=2
```


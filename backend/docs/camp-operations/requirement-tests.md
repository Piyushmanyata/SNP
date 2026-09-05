# Camp operations requirement-to-test checklist

| ID | Test | Status |
| --- | --- | --- |
| C01 | `test_c01_lookup_after_print_before_seen` | implemented |
| C02 | `test_c02_non_operator_cannot_mutate_clinical` | implemented |
| C03 | `test_c03_mark_seen_cannot_confer_seen` | implemented |
| C04 | `test_c04_draft_saves_without_seen_or_fulfilment` | implemented |
| C05 | `test_c05_complete_without_arrival_or_print` | implemented |
| C06 | `test_c06_blank_completion_rejected` | implemented |
| C07 | `test_c07_none_prescribed_completion_awards_point` | implemented |
| C08 | `test_c08_whole_rx_completion_is_atomic` | implemented |
| C09 | `test_c09_orphan_revision_grants_nothing` | implemented |
| C10 | `test_c10_lost_response_reconciles` | implemented |
| C11 | `test_c11_concurrent_completion_one_winner` | implemented |
| C12 | `test_c12_pre_issue_undo_revokes_point` | implemented |
| C13 | `test_c13_old_complete_retry_after_undo` | implemented |
| C14 | `test_c14_undo_after_issue_rejected` | implemented |
| C15 | `test_c15_correction_after_issue_keeps_history` | implemented |
| C16 | `test_c16_second_complete_conflicts` | implemented |
| F01 | `test_f01_issue_without_completion_or_review` | implemented |
| F02 | `test_f02_foreign_revision_rejected` | implemented |
| F03 | `test_f03_stale_review_after_new_revision` | implemented |
| F04 | `test_f04_correction_races_issue` | implemented |
| F05 | `test_f05_retry_recovers_same_allocation` | implemented |
| F06 | `test_f06_double_tap_same_issue` | implemented |
| F07 | `test_f07_last_ot_slot_no_oversubscribe` | implemented |
| F08 | `test_f08_fixed_and_made_exclusive` | implemented |
| F09 | `test_f09_reprint_does_not_confer_care` | implemented |
| P01 | `test_p01_ist_midnight_opens_scheduled_day` | implemented |
| P02 | `test_p02_manual_off_blocks_door_scan` | implemented |
| P03 | `test_p03_manual_early_open_uses_selected_day` | implemented |
| P04 | `test_p04_override_expires_and_does_not_cross_camps` | implemented |
| P05 | `test_p05_stale_print_rejected` | implemented |
| P06 | `test_p06_walkin_vs_repeat_scan` | implemented |
| P07 | `test_p07_partial_camp_setup_no_false_success` | implemented |
| P08 | `test_p08_existing_arrival_no_second_booking` | implemented |
| S01 | `test_s01_lead_direct_no_double_count` | implemented |
| S02 | `test_s02_team_change_keeps_original_credit` | implemented |
| S03 | `test_s03_self_registration_no_staff_point` | implemented |
| S04 | `test_s04_point_follows_valid_completion` | implemented |
| S05 | `test_s05_shared_mobile_not_collapsed` | implemented |
| M01 | `test_m01_self_register_requires_mobile` / SelfRegister.test.js | implemented |
| M02 | `test_m02_reminder_includes_aadhaar_hindi` | implemented |
| A01 | `AadhaarScanner.test.js` permission denial + Retry | implemented |
| A02–A10 | Desk stall/three-session tests; camera classify | implemented |
| U01–U05 | ui 44px primitives; Specs R/L groups; complete vs draft | implemented |

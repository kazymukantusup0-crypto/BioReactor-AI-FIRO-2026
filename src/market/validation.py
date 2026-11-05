"""Five explicit states, separate from price kind and source claims."""
VERIFIED_CURRENT='VERIFIED_CURRENT'
VERIFIED_HISTORICAL='VERIFIED_HISTORICAL'
STALE='STALE'
UNVERIFIED='UNVERIFIED'
UNAVAILABLE='UNAVAILABLE'


def classify(row):
    if row['is_test'] or row['reliability'] not in {'verified_official','verified_manual'}:
        return UNVERIFIED,'test_or_unverified_observation'
    if row.get('source_last_status')=='error':return UNAVAILABLE,'last_source_refresh_failed; cached value retained'
    if row['is_future']:return UNVERIFIED,'not_yet_effective'
    if row['is_superseded']:return VERIFIED_HISTORICAL,'superseded_by_newer_observation'
    if row['is_stale']:return STALE,'age_or_validity_limit_exceeded'
    if row['publication_date_unknown']:return VERIFIED_HISTORICAL,'publication_date_not_confirmed'
    return VERIFIED_CURRENT,'source_date_region_and_age_checked; price_type_still_applies'

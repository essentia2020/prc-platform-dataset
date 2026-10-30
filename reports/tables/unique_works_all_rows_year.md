# unique_works_all_rows_year

Analysis cutoff: 2026-09-30; year 2026 is year_to_date (not annualised).
Additivity: `deduplicated`.
Snapshot: Crossref/Sciety retrieval finished 2026-10-30T14:28:37Z.
Empty cells are not zeros: see `observation_status` and `extraction_status` in the CSV.
The only all-row total; overlapping works are attributed to the class of their earliest event.

| year | year_label | count | partial_year | extraction_status | source_observability_status | observation_status | coverage | temporal_coverage_status | additivity | n_author_initiated_by_earliest_event | n_community_initiated_by_earliest_event | n_mixed_by_earliest_event | blocking_rows |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2001 | 2001 | 14 | false | complete | observable | observed | complete | complete | deduplicated | 14 | 0 | 0 |  |
| 2002 | 2002 | 79 | false | complete | observable | observed | complete | complete | deduplicated | 79 | 0 | 0 |  |
| 2003 | 2003 | 180 | false | complete | observable | observed | complete | complete | deduplicated | 180 | 0 | 0 |  |
| 2004 | 2004 | 285 | false | complete | observable | observed | complete | complete | deduplicated | 285 | 0 | 0 |  |
| 2005 | 2005 | 494 | false | complete | observable | observed | complete | complete | deduplicated | 494 | 0 | 0 |  |
| 2006 | 2006 | 635 | false | complete | observable | observed | complete | complete | deduplicated | 635 | 0 | 0 |  |
| 2007 | 2007 | 816 | false | complete | observable | observed | complete | complete | deduplicated | 816 | 0 | 0 |  |
| 2008 | 2008 | 962 | false | complete | observable | observed | complete | complete | deduplicated | 962 | 0 | 0 |  |
| 2009 | 2009 | 1624 | false | complete | observable | observed | complete | complete | deduplicated | 1624 | 0 | 0 |  |
| 2010 | 2010 | 1797 | false | complete | observable | observed | complete | complete | deduplicated | 1797 | 0 | 0 |  |
| 2011 | 2011 | 2170 | false | complete | observable | observed | complete | complete | deduplicated | 2170 | 0 | 0 |  |
| 2012 | 2012 | 2659 | false | complete | observable | observed | complete | complete | deduplicated | 2659 | 0 | 0 |  |
| 2013 | 2013 | 3042 | false | complete | observable | observed | complete | complete | deduplicated | 3042 | 0 | 0 |  |
| 2014 | 2014 | 3354 | false | complete | observable | observed | complete | complete | deduplicated | 3354 | 0 | 0 |  |
| 2015 | 2015 | 3755 | false | complete | observable | observed | complete | complete | deduplicated | 3755 | 0 | 0 |  |
| 2016 | 2016 | 4491 | false | complete | observable | observed | complete | complete | deduplicated | 4491 | 0 | 0 |  |
| 2017 | 2017 |  | false | complete | not_observable | not_observable | no_data | not_assessable | deduplicated |  |  |  | gates_open_research:partial_coverage |
| 2018 | 2018 |  | false | complete | not_observable | not_observable | no_data | not_assessable | deduplicated |  |  |  | gates_open_research:partial_coverage; prelights:partial_coverage |
| 2019 | 2019 |  | false | complete | not_observable | not_observable | no_data | not_assessable | deduplicated |  |  |  | gates_open_research:partial_coverage; prelights:partial_coverage; prereview:partial_coverage; qeios_hosted_works:partial_coverage; review_commons:source_not_covering |
| 2020 | 2020 |  | false | complete | not_observable | not_observable | no_data | not_assessable | deduplicated |  |  |  | gates_open_research:partial_coverage; prelights:partial_coverage; prereview:partial_coverage; qeios_external_works:partial_coverage; qeios_hosted_works:partial_coverage; review_commons:source_not_covering |
| 2021 | 2021 |  | false | complete | not_observable | not_observable | no_data | not_assessable | deduplicated |  |  |  | gates_open_research:partial_coverage; prelights:partial_coverage; prereview:partial_coverage; qeios_external_works:partial_coverage; qeios_hosted_works:partial_coverage; review_commons:source_not_covering |
| 2022 | 2022 |  | false | complete | not_observable | not_observable | no_data | not_assessable | deduplicated |  |  |  | gates_open_research:partial_coverage; peerref:source_not_covering; prelights:partial_coverage; prereview:partial_coverage; qeios_external_works:partial_coverage; qeios_hosted_works:partial_coverage; review_commons:source_not_covering |
| 2023 | 2023 |  | false | complete | not_observable | not_observable | no_data | not_assessable | deduplicated |  |  |  | gates_open_research:partial_coverage; peerref:source_not_covering; prelights:partial_coverage; prereview:partial_coverage; qeios_external_works:partial_coverage; qeios_hosted_works:partial_coverage; review_commons:source_not_covering; the_unjournal:source_not_covering |
| 2024 | 2024 |  | false | complete | not_observable | not_observable | no_data | not_assessable | deduplicated |  |  |  | gates_open_research:partial_coverage; metaror:source_not_covering; peerref:source_not_covering; prelights:partial_coverage; prereview:partial_coverage; qeios_external_works:partial_coverage; qeios_hosted_works:partial_coverage; review_commons:source_not_covering; the_unjournal:source_not_covering |
| 2025 | 2025 |  | false | complete | not_observable | not_observable | no_data | not_assessable | deduplicated |  |  |  | metaror:source_not_covering; peerref:source_not_covering; prelights:partial_coverage; prereview:partial_coverage; qeios_external_works:partial_coverage; qeios_hosted_works:partial_coverage; review_commons:source_not_covering; the_unjournal:source_not_covering |
| 2026 | 2026 (year_to_date, cutoff 2026-09-30) |  | true | complete | not_observable | not_observable | no_data | not_assessable | deduplicated |  |  |  | metaror:source_not_covering; peerref:source_not_covering; review_commons:source_not_covering; the_unjournal:source_not_covering |

Blank group cells (D-038): the member row and status that block the sum.
- all rows, 2017: gates_open_research:partial_coverage
- all rows, 2018: gates_open_research:partial_coverage; prelights:partial_coverage
- all rows, 2019: gates_open_research:partial_coverage; prelights:partial_coverage; prereview:partial_coverage; qeios_hosted_works:partial_coverage; review_commons:source_not_covering
- all rows, 2020: gates_open_research:partial_coverage; prelights:partial_coverage; prereview:partial_coverage; qeios_external_works:partial_coverage; qeios_hosted_works:partial_coverage; review_commons:source_not_covering
- all rows, 2021: gates_open_research:partial_coverage; prelights:partial_coverage; prereview:partial_coverage; qeios_external_works:partial_coverage; qeios_hosted_works:partial_coverage; review_commons:source_not_covering
- all rows, 2022: gates_open_research:partial_coverage; peerref:source_not_covering; prelights:partial_coverage; prereview:partial_coverage; qeios_external_works:partial_coverage; qeios_hosted_works:partial_coverage; review_commons:source_not_covering
- all rows, 2023: gates_open_research:partial_coverage; peerref:source_not_covering; prelights:partial_coverage; prereview:partial_coverage; qeios_external_works:partial_coverage; qeios_hosted_works:partial_coverage; review_commons:source_not_covering; the_unjournal:source_not_covering
- all rows, 2024: gates_open_research:partial_coverage; metaror:source_not_covering; peerref:source_not_covering; prelights:partial_coverage; prereview:partial_coverage; qeios_external_works:partial_coverage; qeios_hosted_works:partial_coverage; review_commons:source_not_covering; the_unjournal:source_not_covering
- all rows, 2025: metaror:source_not_covering; peerref:source_not_covering; prelights:partial_coverage; prereview:partial_coverage; qeios_external_works:partial_coverage; qeios_hosted_works:partial_coverage; review_commons:source_not_covering; the_unjournal:source_not_covering
- all rows, 2026: metaror:source_not_covering; peerref:source_not_covering; review_commons:source_not_covering; the_unjournal:source_not_covering

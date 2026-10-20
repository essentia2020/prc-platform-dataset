"""Mandatory publisher-account check at the Sciety normalisation boundary."""


class PublisherAccountMismatch(ValueError):
    """A group-scoped response contains an absent or different publisher."""


def validate_docmap_publishers(docmaps, scope):
    """Validate every docmap, including docmaps without evaluation outputs."""
    for docmap in docmaps:
        publisher = docmap.get("publisher") or {}
        account = publisher.get("account") or {}
        identifier = account.get("id", "")
        if not isinstance(identifier, str) or not scope.account_matches(identifier):
            raise PublisherAccountMismatch(
                f"{scope.group_slug}: docmap {docmap.get('id', '')!r} has publisher "
                f"{identifier!r}; expected {scope.publisher_account_url!r}")

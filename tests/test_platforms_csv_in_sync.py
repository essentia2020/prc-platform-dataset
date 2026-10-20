"""Generated CSV registers must equal a fresh export of their YAML sources."""

from src.common import register


def test_platforms_csv_matches_fresh_export():
    fresh = register.render_platforms_csv()
    current = register.PLATFORMS_CSV.read_text(encoding="utf-8")
    assert current == fresh, "config/platforms.csv is stale: run `python -m src.common.register --export`"


def test_excluded_candidates_csv_matches_fresh_export():
    fresh = register.render_excluded_csv()
    current = register.EXCLUDED_CSV.read_text(encoding="utf-8")
    assert current == fresh, "config/excluded_candidates.csv is stale: run `python -m src.common.register --export`"


def test_readme_platform_table_matches_register(repo_root):
    table = register.render_readme_table()
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    assert table in readme, "README platform table is stale: run `python -m src.common.register --readme-table`"

"""Expose failing test diagnostics in GitHub's public run annotations."""
import os


def pytest_runtest_logreport(report):
    if os.environ.get('GITHUB_ACTIONS') and report.failed:
        detail = str(report.longrepr).replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        title = report.nodeid.replace(',', ' ').replace(':', ' ')
        print(f'\n::error title={title}::{detail}', flush=True)

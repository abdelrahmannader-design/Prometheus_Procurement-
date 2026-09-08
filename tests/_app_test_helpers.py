"""Shared setup for tests that instantiate the real Tkinter App.

Critically, this redirects the app's data directory (app_state.json,
exports, backups, error log) to a throwaway temp folder BEFORE the App is
constructed. Without this, every test run would read and write the real
production ~/Documents/ImportDecisionApp/app_state.json -- on a
developer's machine that's merely annoying, but on a user's real Windows
install (where run_tests.bat is meant to be run) it would corrupt their
actual procurement data with test contracts. Never remove this isolation.
"""
import shutil
import tempfile


def start_isolated_app(prometheus_module):
    """Patch prometheus_module.get_app_data_dir() to a temp dir, construct
    the App, and return (app, tmp_dir, restore_fn). Call restore_fn() in
    tearDownClass after app.destroy()."""
    tmp_dir = tempfile.mkdtemp(prefix="prometheus_test_")
    original = prometheus_module.get_app_data_dir
    prometheus_module.get_app_data_dir = lambda: tmp_dir

    app = prometheus_module.App()
    app.withdraw()

    def restore():
        prometheus_module.get_app_data_dir = original
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return app, tmp_dir, restore

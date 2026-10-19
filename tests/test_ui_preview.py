"""The test executable must never install or announce production updates."""
from unittest.mock import patch


def test_preview_updates_are_disabled_and_preferences_are_isolated(monkeypatch):
    import settings
    original = settings.data_dir
    try:
        from experimental.ui_preview import PreviewAPI, preview_data_dir
        with patch('updater.check_update') as check, patch('updater.stage_update') as install:
            api = PreviewAPI()
            assert api.check_update()['experimental'] is True
            assert api.check_update()['available'] is False
            assert 'error' in api.install_update()
            check.assert_not_called(); install.assert_not_called()
        assert preview_data_dir().name == 'Kupotube-UI-Preview'
    finally:
        settings.data_dir = original

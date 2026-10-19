"""UI-only test executable. Uses isolated settings and never contacts the updater."""
import os
from pathlib import Path

import settings


def preview_data_dir():
    return Path(os.environ.get('LOCALAPPDATA',Path.home() / '.local' / 'share')) / 'Kupotube-UI-Preview'


# Route the existing settings/cookie helpers to this test copy's own data folder.
settings.data_dir = preview_data_dir
import desktop


class PreviewAPI(desktop.DesktopAPI):
    def check_update(self):
        return {'available':False,'experimental':True,'current':'0.3.8-ui-preview.4'}

    def install_update(self):
        return {'error':'O atualizador está desativado nesta prévia da interface.'}


def main():
    desktop.DesktopAPI = PreviewAPI
    desktop.main()


if __name__ == '__main__':
    main()

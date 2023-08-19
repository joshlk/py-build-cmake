from copy import copy
from ...common import BuildPaths, Module
import shutil
from ..util import copy_pkg_source_to

def write_editable_links(paths: BuildPaths, module: Module):
    paths = copy(paths)
    cache_dir = paths.build_dir
    cache_dir.mkdir(exist_ok=True)
    paths.staging_dir = cache_dir / 'editable'
    shutil.rmtree(paths.staging_dir, ignore_errors=True)
    paths.staging_dir.mkdir()
    copy_pkg_source_to(paths.staging_dir, module, symlink=True)
    pth_file = paths.pkg_staging_dir / f'{module.name}.pth'
    pth_file.parent.mkdir(exist_ok=True)
    pth_file.write_text(str(paths.staging_dir))
    return paths

import platform
from pprint import pprint
import sys
import os
from pathlib import Path
from string import Template
import re
import shutil
import textwrap
from typing import Any, Dict, List, Optional, Union
import tempfile
from subprocess import run as sp_run
from glob import glob

from .config import Config


class _BuildBackend(object):

    def __init__(self) -> None:
        self.verbose = False

    fileopt = {'encoding': 'utf-8'}

    def get_requires_for_build_wheel(self, config_settings=None):
        """https://www.python.org/dev/peps/pep-0517/#get-requires-for-build-wheel"""
        return []

    def get_requires_for_build_editable(self, config_settings=None):
        """https://www.python.org/dev/peps/pep-0660/#get-requires-for-build-editable"""
        return self.get_requires_for_build_wheel(config_settings)

    def get_requires_for_build_sdist(self, config_settings=None):
        """https://www.python.org/dev/peps/pep-0517/#get-requires-for-build-sdist"""
        return self.get_requires_for_build_wheel(config_settings)

    def build_wheel(self,
                    wheel_directory,
                    config_settings=None,
                    metadata_directory=None):
        """https://www.python.org/dev/peps/pep-0517/#build-wheel"""
        assert metadata_directory is None

        # Parse options
        self.parse_config_settings(config_settings)

        # Build wheel
        with tempfile.TemporaryDirectory() as tmp_build_dir:
            whl_name = self.build_wheel_in_dir(wheel_directory, tmp_build_dir)
        return whl_name

    def build_editable(self,
                       wheel_directory,
                       config_settings=None,
                       metadata_directory=None):
        """https://www.python.org/dev/peps/pep-0660/#build-editable"""
        assert metadata_directory is None

        # Parse options
        self.parse_config_settings(config_settings)

        # Build wheel
        with tempfile.TemporaryDirectory() as tmp_build_dir:
            whl_name = self.build_wheel_in_dir(wheel_directory,
                                               tmp_build_dir,
                                               editable=True)
        return whl_name

    def build_sdist(self, sdist_directory, config_settings=None):
        """https://www.python.org/dev/peps/pep-0517/#build-sdist"""
        sdist_directory = Path(sdist_directory)
        src_dir = Path().resolve()

        # Parse options
        self.parse_config_settings(config_settings)

        # Load metadata
        from .config import normalize_name_wheel
        from flit_core.common import Module, make_metadata
        pyproject = src_dir / 'pyproject.toml'
        cfg = self.read_metadata(pyproject)
        norm_name = normalize_name_wheel(cfg.metadata['name'])
        pkg = Module(norm_name, src_dir / cfg.module.get('directory', '.'))
        metadata = make_metadata(pkg, cfg)
        metadata.version = self.normalize_version(metadata.version)

        # Export dist
        from flit_core.sdist import SdistBuilder
        rel_pyproject = os.path.relpath(pyproject, src_dir)
        extra_files = [str(rel_pyproject)] + cfg.referenced_files
        sdist_cfg = cfg.sdist[self.get_os_name()]
        sdist_builder = SdistBuilder(pkg, metadata, src_dir, None,
                                     cfg.entrypoints, extra_files,
                                     sdist_cfg.get('include_patterns', []),
                                     sdist_cfg.get('exclude_patterns', []))
        sdist_tar = sdist_builder.build(Path(sdist_directory))
        return os.path.relpath(sdist_tar, sdist_directory)

    @staticmethod
    def get_os_name():
        return {
            "Linux": "linux",
            "Windows": "windows",
            "Darwin": "mac",  # TODO: untested
        }[platform.system()]

    def parse_config_settings(self, config_settings: Optional[Dict]):
        if config_settings is None:
            return
        if config_settings.keys() & {'verbose', 'v'}:
            self.verbose = True

    def read_metadata(self, pyproject):
        from .config import read_metadata
        cfg = read_metadata(pyproject)
        if self.verbose:
            print("\npy-build-cmake options")
            print("======================")
            print("module:")
            pprint(cfg.module)
            print("sdist:")
            pprint(cfg.sdist)
            print("cmake:")
            pprint(cfg.cmake)
            print("stubgen:")
            pprint(cfg.stubgen)
            print("cross:")
            pprint(cfg.cross)
            print("======================\n")
        return cfg

    def build_wheel_in_dir(self,
                           wheel_directory,
                           tmp_build_dir,
                           editable=False):
        wheel_directory = Path(wheel_directory)
        tmp_build_dir = Path(tmp_build_dir)
        staging_dir = tmp_build_dir / 'staging'
        src_dir = Path().resolve()

        # Load metadata
        from .config import normalize_name_wheel
        from flit_core.common import Module, make_metadata
        cfg = self.read_metadata(src_dir / 'pyproject.toml')
        norm_name = normalize_name_wheel(cfg.metadata['name'])
        pkg = Module(norm_name, src_dir / cfg.module.get('directory', '.'))
        metadata = make_metadata(pkg, cfg)
        metadata.version = self.normalize_version(metadata.version)

        # Copy the module source files to the temporary folder
        if not editable:
            self.copy_pkg_source_to(staging_dir, src_dir, pkg)
        else:
            self.write_editable_wrapper(staging_dir, src_dir, pkg)

        # Create dist-info folder
        distinfo = staging_dir / f'{norm_name}-{metadata.version}.dist-info'
        os.makedirs(distinfo, exist_ok=True)

        # Write metadata
        metadata_path = distinfo / 'METADATA'
        with open(metadata_path, 'w', **self.fileopt) as f:
            metadata.write_metadata_file(f)

        # Write or copy license
        self.write_license_files(cfg.license, src_dir, distinfo)

        # TODO: write entrypoints
        self.write_entrypoints(cfg)

        # Generate .pyi stubs
        if cfg.stubgen is not None and not editable:
            self.generate_stubs(tmp_build_dir, staging_dir, pkg, cfg.stubgen)

        # Configure, build and install the CMake project
        if cfg.cmake:
            self.do_native_cross_cmake_build(tmp_build_dir, staging_dir,
                                             src_dir, cfg, metadata)

        # Create wheel
        whl_name = self.create_wheel(wheel_directory, staging_dir, cfg,
                                     norm_name, metadata.version)
        return whl_name

    def do_native_cross_cmake_build(self, tmp_build_dir, staging_dir, src_dir,
                                    cfg, metadata):
        """If not cross-compiling, just do a regular CMake build+install.
        When cross-compiling, do a cross-build+install (using the provided 
        CMake toolchain file).
        If cfg.cross['copy_from_native_build'] is set, before cross-compiling, 
        first a normal build+install is performed to a separate directory, then
        the cross-build+install is performed, and finally the installed files
        from the native build that match the patterns in
        cfg.cross['copy_from_native_build'] are copied to the installation
        directory of the cross-build for packaging."""
        # When cross-compiling, optionally do a native build first
        native_install_dir = None
        native_cmake_cfg = cfg.cmake[self.get_os_name()]
        if cfg.cross and (cfnb := 'copy_from_native_build') in cfg.cross:
            native_install_dir = tmp_build_dir / 'native-install'
            self.run_cmake(src_dir, native_install_dir, metadata,
                           native_cmake_cfg, None, native_install_dir)
        # Then do the actual build
        cmake_cfg = cfg.cmake['cross'] if cfg.cross else native_cmake_cfg
        self.run_cmake(src_dir, staging_dir, metadata, cmake_cfg, cfg.cross,
                       native_install_dir)
        # Finally, move the files from the native build to the staging area
        if native_install_dir:
            self.copy_native_install(staging_dir, native_install_dir,
                                     cfg.cross[cfnb])

    def copy_native_install(self, staging_dir, native_install_dir,
                            native_install_patterns):
        """Copy the files that match the patterns from the native installation
        directory to the wheel staging directory."""
        for pattern in native_install_patterns:
            matches = sorted(glob(str(native_install_dir / pattern)))
            for path in matches:
                path = Path(path)
                rel = path.relative_to(native_install_dir)
                path.parent.mkdir(parents=True, exist_ok=True)
                print('-- Moving:', path, '->', staging_dir / rel.parent)
                shutil.move(path, staging_dir / rel.parent)
                # TODO: what if the folder already exists?
            if not matches:
                raise RuntimeError(
                    "Native build installed no files that matched the "
                    "pattern '" + pattern + "'")
        shutil.rmtree(native_install_dir)

    def normalize_version(self, version):
        from distlib.version import NormalizedVersion
        norm_version = str(NormalizedVersion(version))
        return norm_version

    def write_license_files(self, license, srcdir: Path, distinfo_dir: Path):
        if 'text' in license:
            with open(distinfo_dir / 'LICENSE', 'w', encoding='utf-8') as f:
                f.write(license['text'])
        elif 'file' in license:
            shutil.copy2(srcdir / license['file'], distinfo_dir)

    def write_editable_wrapper(self, tmp_build_dir: Path, src_dir: Path, pkg):
        # Write a fake __init__.py file that points to the development folder
        tmp_pkg = tmp_build_dir / pkg.name
        os.makedirs(tmp_pkg, exist_ok=True)
        special_dunders = [
            '__builtins__', '__cached__', '__file__', '__loader__', '__name__',
            '__package__', '__path__', '__spec__'
        ]
        content = f"""\
            # First extend the search path with the development folder
            __spec__.submodule_search_locations.insert(0, "{pkg.path}")
            # Now manually import the development __init__.py
            from importlib import util as _util
            _spec = _util.spec_from_file_location("{pkg.name}",
                                                  "{pkg.path}/__init__.py")
            _mod = _util.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            # After importing, add its symbols to our global scope
            _vars = _mod.__dict__.copy()
            for _k in ['{"','".join(special_dunders)}']: _vars.pop(_k)
            globals().update(_vars)
            del _k
            del _spec
            del _mod
            del _vars
            del _util
            """
        (tmp_pkg / '__init__.py').write_text(textwrap.dedent(content),
                                             **self.fileopt)
        # Add the py.typed file if it exists, so mypy picks up the stubs for
        # the C++ extensions
        py_typed: Path = pkg.path / 'py.typed'
        if py_typed.exists():
            shutil.copy2(py_typed, tmp_pkg)
        # Write a path file so IDEs find the correct files as well
        (tmp_build_dir / f'{pkg.name}.pth').write_text(str(pkg.path.parent))

    def copy_pkg_source_to(self, tmp_build_dir, src_dir, pkg):
        for mod_file in pkg.iter_files():
            rel_path = os.path.relpath(mod_file, pkg.path.parent)
            dst = tmp_build_dir / rel_path
            os.makedirs(dst.parent, exist_ok=True)
            shutil.copy2(mod_file, dst, follow_symlinks=False)

    def run(self, *args, **kwargs):
        """Wrapper around subproces.run that optionally prints the command."""
        if self.verbose:
            pprint([*args])
            pprint(kwargs)
        return sp_run(*args, **kwargs)

    def generate_stubs(self, tmp_build_dir, staging_dir, pkg, cfg: Dict[str,
                                                                        Any]):
        """Generate stubs (.pyi) using mypy stubgen."""
        args = ['stubgen'] + cfg.get('args', [])
        cfg.setdefault('packages', [pkg.name] if pkg.is_package else [])
        for p in cfg['packages']:
            args += ['-p', p]
        cfg.setdefault('modules', [pkg.name] if not pkg.is_package else [])
        for m in cfg['modules']:
            args += ['-m', m]
        args += cfg.get('files', [])
        # Add output folder argument if not already specified in cfg['args']
        if 'args' not in cfg or not ({'-o', '--output'} & set(cfg['args'])):
            args += ['-o', staging_dir]
        env = os.environ.copy()
        env.setdefault('MYPY_CACHE_DIR', str(tmp_build_dir))
        # Call mypy stubgen in a subprocess
        self.run(args, cwd=pkg.path.parent, check=True, env=env)

    def run_cmake(self,
                  pkgdir,
                  install_dir,
                  metadata,
                  cmake_cfg,
                  cross_cfg,
                  native_install_dir=None):
        """Configure, build and install using CMake."""
        # Source and build folders
        srcdir = Path(cmake_cfg.get('source_path', pkgdir)).resolve()
        builddir = pkgdir / '.py-build-cmake_cache'
        builddir = Path(cmake_cfg.get('build_path', builddir))
        if not builddir.is_absolute():
            builddir = pkgdir / builddir
        buildconfig = self.get_build_config_name(cross_cfg)
        builddir = builddir / buildconfig
        builddir = builddir.resolve()
        # Environment variables
        cmake_env = os.environ.copy()
        if (f := 'env') in cmake_cfg:
            for k, v in cmake_cfg[f].items():
                cmake_env[k] = Template(v).substitute(cmake_env)

        # Configure
        configure_cmd = [
            'cmake',
            '-B',
            str(builddir),
            '-S',
            str(srcdir),
            '-D',
            'VERIFY_VERSION=' + metadata.version,
        ]
        if cross_cfg:
            toolchain = (pkgdir / cross_cfg['toolchain_file']).resolve()
            configure_cmd += [
                '-D', 'CMAKE_TOOLCHAIN_FILE:FILEPATH=' + str(toolchain)
            ]
        else:
            configure_cmd += [
                '-D', 'Python3_ROOT_DIR:PATH=' + sys.prefix, '-D',
                'Python3_FIND_REGISTRY=NEVER', '-D',
                'Python3_FIND_STRATEGY=LOCATION'
            ]
        if native_install_dir:
            configure_cmd += [
                '-D', 'PY_BUILD_CMAKE_NATIVE_INSTALL_DIR:PATH=' +
                str(native_install_dir)
            ]
        configure_cmd += cmake_cfg.get('args', [])  # User-supplied arguments
        for k, v in cmake_cfg.get('options', {}).items():  # -D {option}={val}
            configure_cmd += ['-D', k + '=' + v]
        if (f := 'build_type') in cmake_cfg:  # -D CMAKE_BUILD_TYPE={type}
            configure_cmd += ['-D', 'CMAKE_BUILD_TYPE=' + cmake_cfg[f]]
            cmake_cfg.setdefault('config', cmake_cfg[f])
        if (f := 'generator') in cmake_cfg:  # -G {generator}
            configure_cmd += ['-G', cmake_cfg[f]]
        self.run(configure_cmd, check=True, env=cmake_env)

        # Build
        build_cmd = ['cmake', '--build', str(builddir)]
        build_cmd += cmake_cfg.get('build_args', [])  # User-supplied arguments
        if (f := 'config') in cmake_cfg:  # --config {config}
            build_cmd += ['--config', cmake_cfg[f]]
        if (f := 'build_tool_args') in cmake_cfg:
            build_cmd += ['--'] + cmake_cfg[f]
        self.run(build_cmd, check=True, env=cmake_env)

        # Install
        for component in cmake_cfg['install_components']:
            install_cmd = [
                'cmake', '--install',
                str(builddir), '--prefix',
                str(install_dir)
            ]
            install_cmd += cmake_cfg.get('install_args', [])
            if (f := 'config') in cmake_cfg:  # --config {config}
                install_cmd += ['--config', cmake_cfg[f]]
            if component:
                install_cmd += ['--component', component]
            print('Installing component', component or 'all')
            self.run(install_cmd, check=True, env=cmake_env)

    @staticmethod
    def get_build_config_name(cross_cfg):
        from distlib.wheel import IMPVER, ABI, ARCH
        buildconfig = '-'.join([IMPVER, ABI, ARCH])
        if cross_cfg:
            buildconfig = '-'.join(
                map(lambda x: x[0],
                    _BuildBackend.get_cross_tags(cross_cfg).values()))
        return buildconfig

    def write_entrypoints(self, cfg: Config):
        if cfg.entrypoints:
            print(cfg.entrypoints)
            raise RuntimeWarning("Entrypoints are not currently supported")

    def create_wheel(self, wheel_directory, tmp_build_dir, cfg, norm_name,
                     norm_version):
        from distlib.wheel import Wheel
        whl = Wheel()
        whl.name = norm_name
        whl.version = norm_version
        libdir = 'platlib' if cfg.cmake is not None else 'purelib'
        paths = {'prefix': str(tmp_build_dir), libdir: str(tmp_build_dir)}
        whl.dirname = wheel_directory
        tags = None
        if cfg.cross:
            tags = self.get_cross_tags(cfg.cross)
        wheel_path = whl.build(paths, tags=tags, wheel_version=(1, 0))
        whl_name = os.path.relpath(wheel_path, wheel_directory)
        return whl_name

    @staticmethod
    def get_cross_tags(crosscfg):
        return {
            'pyver': [crosscfg['implementation'] + crosscfg['version']],
            'abi': [crosscfg['abi']],
            'arch': [crosscfg['arch']],
        }

    def iter_files(self, stagedir):
        """Iterate over the files contained in the given folder.

        Yields absolute paths - caller may want to make them relative.
        Excludes any __pycache__ and *.pyc files."""

        # https://github.com/pypa/flit/blob/a4524758604107bde8c77b5816612edb76a604aa/flit_core/flit_core/common.py#L73

        def _include(path):
            name = os.path.basename(path)
            return name != '__pycache__' and not name.endswith('.pyc')

        # Ensure we sort all files and directories so the order is stable
        for dirpath, dirs, files in os.walk(str(stagedir)):
            for file in sorted(files):
                full_path = os.path.join(dirpath, file)
                if _include(full_path):
                    yield full_path

            dirs[:] = [d for d in sorted(dirs) if _include(d)]


_BACKEND = _BuildBackend()
get_requires_for_build_wheel = _BACKEND.get_requires_for_build_wheel
get_requires_for_build_sdist = _BACKEND.get_requires_for_build_sdist
get_requires_for_build_editable = _BACKEND.get_requires_for_build_editable
build_wheel = _BACKEND.build_wheel
build_sdist = _BACKEND.build_sdist
build_editable = _BACKEND.build_editable

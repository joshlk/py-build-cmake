import tempfile
from pathlib import Path
from typing import Dict, Optional
import logging
import os

from . import config
from .export import metadata as export_metadata
from .build import _BuildBackend as std_backend
from .common import BuildPaths, PackageInfo, Config, ComponentConfig
from .commands.cmd_runner import CommandRunner
from .config import load as config_load

logger = logging.getLogger(__name__)


class _BuildComponentBackend(object):
    # --- Constructor ---------------------------------------------------------

    def __init__(self) -> None:
        self.runner: CommandRunner = CommandRunner()

    @property
    def verbose(self):
        return self.runner.verbose

    # --- Methods required by PEP 517 -----------------------------------------

    def get_requires_for_build_wheel(self, config_settings=None):
        """https://www.python.org/dev/peps/pep-0517/#get-requires-for-build-wheel"""
        self.parse_config_settings(config_settings)

        comp_pyproject = Path("pyproject.toml").resolve()
        comp_cfg = self.read_component_config(
            comp_pyproject, config_settings, self.verbose
        )
        cfg = std_backend.read_config(
            Path(comp_cfg.component["main_project"]) / "pyproject.toml",
            config_settings,
            self.verbose,
        )
        return std_backend.get_requires_build_project(config_settings, cfg, self.runner)

    def get_requires_for_build_editable(self, config_settings=None):
        """https://www.python.org/dev/peps/pep-0660/#get-requires-for-build-editable"""
        return self.get_requires_for_build_wheel(config_settings)

    def get_requires_for_build_sdist(self, config_settings=None):
        """https://www.python.org/dev/peps/pep-0517/#get-requires-for-build-sdist"""
        return []

    def build_wheel(
        self, wheel_directory, config_settings=None, metadata_directory=None
    ):
        """https://www.python.org/dev/peps/pep-0517/#build-wheel"""
        assert metadata_directory is None

        # Parse options
        self.parse_config_settings(config_settings)

        # Build wheel
        with tempfile.TemporaryDirectory() as tmp_build_dir:
            whl_name = self.build_wheel_in_dir(
                wheel_directory, tmp_build_dir, config_settings
            )
        return whl_name

    def build_editable(
        self, wheel_directory, config_settings=None, metadata_directory=None
    ):
        raise NotImplementedError(
            "Editable installation not supported for individual components."
        )

    def build_sdist(self, sdist_directory, config_settings=None):
        raise NotImplementedError(
            "Source distribution not supported for individual components."
        )

    # --- Parsing config options and metadata ---------------------------------

    def parse_config_settings(self, config_settings: Optional[Dict]):
        try:
            level = std_backend.get_log_level(config_settings)
            logging.basicConfig(level=level)
        except ValueError as e:
            logger.error("Invalid log level specified", exc_info=e)
        self.runner.verbose = std_backend.is_verbose_enabled(config_settings)

    @staticmethod
    def read_all_metadata(src_dir, config_settings, verbose):
        cfg = config_load.read_full_component_config_checked(
            src_dir / "pyproject.toml", config_settings, verbose
        )
        return cfg

    # --- Building wheels -----------------------------------------------------

    def build_wheel_in_dir(
        self, wheel_dir, tmp_build_dir, config_settings, editable=False
    ):
        """This is the main function that contains all steps necessary to build
        a complete wheel package, including the CMake builds etc."""
        comp_source_dir = Path().resolve()

        # Load metadata from the current (component) pyproject.toml file
        comp_cfg = self.read_all_metadata(
            comp_source_dir, config_settings, self.verbose
        )

        # Load the config from the main pyproject.toml file
        src_dir = Path(comp_cfg.component["main_project"]).resolve()
        cfg, module = std_backend.read_all_metadata(
            src_dir, config_settings, self.verbose
        )
        cmake_cfg = std_backend.get_cmake_config(cfg)
        pkg_info = PackageInfo(
            version=comp_cfg.standard_metadata.version,
            package_name=comp_cfg.package_name,
            module_name=module.name if module is not None else "",
        )

        # Set up all paths
        paths = std_backend.get_default_paths(
            wheel_dir, tmp_build_dir, src_dir, cfg, cmake_cfg
        )

        # Create dist-info folder
        distinfo_dir = f"{pkg_info.package_name}-{pkg_info.version}.dist-info"
        distinfo_dir = paths.pkg_staging_dir / distinfo_dir
        os.makedirs(distinfo_dir, exist_ok=True)

        # Write metadata, license and entry points to Wheel's distinfo
        export_metadata.write_metadata(comp_cfg, distinfo_dir)
        export_metadata.write_license_files(comp_cfg, distinfo_dir)
        export_metadata.write_entry_points(comp_cfg, distinfo_dir)

        # Configure, build and install the CMake project
        if cmake_cfg:
            cmaker = self.get_cmaker(
                paths.source_dir,
                paths.build_dir,
                paths.staging_dir,
                cmake_cfg,
                cfg.cross,
                pkg_info,
                comp_cfg,
                runner=self.runner,
            )
            if not comp_cfg.component["install_only"]:
                cmaker.build()
            cmaker.install()

        # Create wheel
        whl_name = std_backend.create_wheel(paths, cfg, cmake_cfg, pkg_info)
        return whl_name

    # --- CMake builds --------------------------------------------------------

    @staticmethod
    def get_cmaker(
        source_dir: Path,
        build_dir: Path,
        install_dir: Optional[Path],
        cmake_cfg: dict,
        cross_cfg: Optional[dict],
        package_info: PackageInfo,
        comp_cfg: ComponentConfig,
        **kwargs,
    ):
        cmaker = std_backend.get_cmaker(
            source_dir=source_dir,
            build_dir=build_dir,
            install_dir=install_dir,
            cmake_cfg=cmake_cfg,
            cross_cfg=cross_cfg,
            package_info=package_info,
            **kwargs,
        )
        comp = comp_cfg.component
        if "build_presets" in comp:
            cmaker.build_settings.presets = comp["build_presets"]
        if "install_presets" in comp:
            cmaker.install_settings.presets = comp["install_presets"]
        if "build_args" in comp:
            cmaker.build_settings.args = comp["build_args"]
        if "build_tool_args" in comp:
            cmaker.build_settings.tool_args = comp["build_tool_args"]
        if "install_args" in comp:
            cmaker.install_settings.args = comp["install_args"]
        if "install_components" in comp:
            cmaker.install_settings.components = comp["install_components"]
        return cmaker


_BACKEND = _BuildComponentBackend()
get_requires_for_build_wheel = _BACKEND.get_requires_for_build_wheel
get_requires_for_build_sdist = _BACKEND.get_requires_for_build_sdist
get_requires_for_build_editable = _BACKEND.get_requires_for_build_editable
build_wheel = _BACKEND.build_wheel
build_sdist = _BACKEND.build_sdist
build_editable = _BACKEND.build_editable

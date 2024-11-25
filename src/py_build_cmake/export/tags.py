from __future__ import annotations

import re
from copy import copy
from typing import Any

from .native_tags import WheelTags, get_native_tags


def get_cross_tags(crosscfg: dict[str, Any]) -> WheelTags:
    """Get the PEP 425 tags to use when cross-compiling."""
    tags = get_native_tags()
    if "implementation" in crosscfg and "version" in crosscfg:
        tags["pyver"] = [crosscfg["implementation"] + crosscfg["version"]]
    if "abi" in crosscfg:
        tags["abi"] = [crosscfg["abi"]]
    if "arch" in crosscfg:
        tags["arch"] = [crosscfg["arch"]]
    return tags


def convert_abi_tag(abi_tag: str, wheel_cfg: dict) -> str:
    """Set the ABI tag to 'none' or 'abi3', depending on the config options
    specified by the user."""
    if wheel_cfg["python_abi"] == "auto":
        return abi_tag
    elif wheel_cfg["python_abi"] == "none":
        return "none"
    elif wheel_cfg["python_abi"] == "abi3":
        # Only use abi3 if we're actually building for CPython
        m = re.match(r"^cp(\d+).*$", abi_tag)
        if m and int(m[1]) >= wheel_cfg["abi3_minimum_cpython_version"]:
            return "abi3"
        return abi_tag
    else:
        msg = "Unsupported python_abi"
        raise AssertionError(msg)


def convert_wheel_tags(tags: dict[str, list[str]], wheel_cfg: dict) -> WheelTags:
    """Apply convert_abi_tag to each of the abi tags and override any tags
    that were specified in the config file."""
    tags = copy(tags)
    cvt_abi = lambda tag: convert_abi_tag(tag, wheel_cfg)
    tags["abi"] = list(map(cvt_abi, tags["abi"]))
    if wheel_cfg["python_tag"] != ["auto"]:
        pyver = tags["pyver"][0]
        pyver_cfg = wheel_cfg["python_tag"]
        tags["pyver"] = [pyver if v == "auto" else v for v in pyver_cfg]
        tags["pyver"] = list(dict.fromkeys(tags["pyver"]))  # unique tags
    if "abi_tag" in wheel_cfg:
        tags["abi"] = wheel_cfg["abi_tag"]
    if "platform_tag" in wheel_cfg:
        plat = wheel_cfg["platform_tag"]  # Platform tags specified by the user
        guess = tags["arch"]  # Tags guessed based on the current interpreter
        # If the user-specified tags contain "guess", replace it by the guesses
        tags["arch"] = [x for t in plat for x in (guess if t == "guess" else [t])]
    return tags


def is_pure(wheel_cfg: dict, cmake_cfg: dict | None) -> bool:
    """Check if the package is a pure-Python package without platform-
    specific binaries."""
    if "pure_python" in wheel_cfg:
        return wheel_cfg["pure_python"]
    return not cmake_cfg

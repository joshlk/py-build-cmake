from pprint import pprint

import pytest
import py_build_cmake.newconfig as nc
from flit_core.config import ConfigError


def gen_test_opts():
    leaf11 = nc.StrConfigOption("leaf11")
    leaf12 = nc.StrConfigOption("leaf12")
    mid1 = nc.ConfigOption("mid1")
    mid1.insert(leaf11)
    mid1.insert(leaf12)
    leaf21 = nc.StrConfigOption("leaf21")
    leaf22 = nc.StrConfigOption("leaf22")
    mid2 = nc.ConfigOption("mid2")
    mid2.insert(leaf21)
    mid2.insert(leaf22)
    trunk = nc.ConfigOption("trunk")
    trunk.insert(mid1)
    trunk.insert(mid2)
    opts = nc.ConfigOption("root")
    opts.insert(trunk)
    return opts


def test_iter():
    opts = gen_test_opts()
    result = [p for p in opts.iter_opt_paths()]
    expected = [
        ('trunk', ),
        ('trunk', 'mid1'),
        ('trunk', 'mid1', 'leaf11'),
        ('trunk', 'mid1', 'leaf12'),
        ('trunk', 'mid2'),
        ('trunk', 'mid2', 'leaf21'),
        ('trunk', 'mid2', 'leaf22'),
    ]
    print(result)
    assert result == expected


def test_iter_leaf():
    opts = gen_test_opts()
    result = [p for p in opts.iter_leaf_opt_paths()]
    expected = [
        ('trunk', 'mid1', 'leaf11'),
        ('trunk', 'mid1', 'leaf12'),
        ('trunk', 'mid2', 'leaf21'),
        ('trunk', 'mid2', 'leaf22'),
    ]
    print(result)
    assert result == expected


def test_update_defaults():
    opts = gen_test_opts()
    trunk = opts[nc.pth('trunk')]
    assert trunk.name == "trunk"
    mid1 = opts[nc.pth('trunk/mid1')]
    assert mid1.name == "mid1"
    leaf12 = opts[nc.pth('trunk/mid1/leaf12')]
    assert leaf12.name == "leaf12"

    cfg = nc.ConfigNode.from_dict({})
    trunk.default = nc.DefaultValueValue({})
    res = opts.update_default(cfg, nc.pth('trunk'))
    assert res is not None and res.value == {}
    assert cfg.to_dict() == {"trunk": {}}

    cfg = nc.ConfigNode.from_dict({})
    leaf12.default = nc.DefaultValueValue("d12")
    res = opts.update_default(cfg, nc.pth('trunk/mid1/leaf12'))
    assert res is not None and res.value == "d12"
    assert cfg.to_dict() == {"trunk": {}}

    cfg = nc.ConfigNode.from_dict({})
    mid1.default = nc.DefaultValueValue({})
    res = opts.update_default(cfg, nc.pth('trunk/mid1/leaf12'))
    assert res is not None and res.value == "d12"
    assert cfg.to_dict() == {"trunk": {"mid1": {"leaf12": "d12"}}}

    cfg = nc.ConfigNode.from_dict({})
    print(cfg)
    print(cfg.value)
    print(cfg.sub)
    trunk.default = nc.NoDefaultValue()
    res = opts.update_default(cfg, nc.pth('trunk/mid1/leaf12'))
    assert res is not None and res.value == "d12"
    print(cfg)
    print(cfg.value)
    print(cfg.sub)
    assert cfg.to_dict() == {}


def test_override0():
    opts = gen_test_opts()
    d = {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "21",
                "leaf22": "22",
            },
        },
        # No override
    }
    opts[nc.pth('')].insert(
        nc.OverrideConfigOption(
            'override_mid2',
            '',
            targetpath=nc.pth('trunk/mid2'),
        ))
    cfg = nc.ConfigNode.from_dict(d)
    opts.verify_all(cfg)
    opts.override_all(cfg)
    assert cfg.to_dict() == {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "21",
                "leaf22": "22",
            },
        },
    }


def test_override1():
    opts = gen_test_opts()
    d = {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "21",
                "leaf22": "22",
            },
        },
        "override_mid2": {
            "leaf21": "23"
        }
    }
    opts[nc.pth('')].insert(
        nc.OverrideConfigOption(
            'override_mid2',
            '',
            targetpath=nc.pth('trunk/mid2'),
        ))
    cfg = nc.ConfigNode.from_dict(d)
    opts.verify_all(cfg)
    opts.override_all(cfg)
    assert cfg.to_dict() == {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "23",
                "leaf22": "22",
            },
        },
        "override_mid2": {
            "leaf21": "23"
        }
    }


def test_override2():
    opts = gen_test_opts()
    d = {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "21",
                "leaf22": "22",
            },
        },
        "override_mid2": {
            "leaf21": "31",
            "leaf22": "32",
        },
    }
    opts[nc.pth('')].insert(
        nc.OverrideConfigOption(
            'override_mid2',
            '',
            targetpath=nc.pth('trunk/mid2'),
        ))
    cfg = nc.ConfigNode.from_dict(d)
    opts.verify_all(cfg)
    opts.override_all(cfg)
    assert cfg.to_dict() == {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "31",
                "leaf22": "32",
            },
        },
        "override_mid2": {
            "leaf21": "31",
            "leaf22": "32",
        },
    }


def test_override_trunk():
    opts = gen_test_opts()
    d = {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "21",
                "leaf22": "22",
            },
        },
        "override_trunk": {
            "mid1": {
                "leaf12": "33",
            },
            "mid2": {
                "leaf21": "31",
                "leaf22": "32",
            },
        },
    }
    opts[nc.pth('')].insert(
        nc.OverrideConfigOption(
            'override_trunk',
            '',
            targetpath=nc.pth('trunk'),
        ))
    cfg = nc.ConfigNode.from_dict(d)
    opts.verify_all(cfg)
    opts.override_all(cfg)
    assert cfg.to_dict() == {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "33",
            },
            "mid2": {
                "leaf21": "31",
                "leaf22": "32",
            },
        },
        "override_trunk": {
            "mid1": {
                "leaf12": "33",
            },
            "mid2": {
                "leaf21": "31",
                "leaf22": "32",
            },
        },
    }


def test_verify_override_unknown_keys():
    opts = gen_test_opts()
    d = {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "21",
                "leaf22": "22",
            },
        },
        "override_mid2": {
            "blahblah": "31",
            "leaf22": "32",
        },
    }
    opts[nc.pth('')].insert(
        nc.OverrideConfigOption(
            'override_mid2',
            '',
            targetpath=nc.pth('trunk/mid2'),
        ))
    cfg = nc.ConfigNode.from_dict(d)
    expected = 'Unkown options in override_mid2: blahblah'
    with pytest.raises(ConfigError, match=expected) as e:
        opts.verify_all(cfg)
    print(e)


def test_override_trunk_unknown_keys():
    opts = gen_test_opts()
    d = {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "21",
                "leaf22": "22",
            },
        },
        "override_trunk": {
            "mid1": {
                "azertyop": "33",
            },
        },
    }
    opts[nc.pth('')].insert(
        nc.OverrideConfigOption(
            'override_trunk',
            '',
            targetpath=nc.pth('trunk'),
        ))
    cfg = nc.ConfigNode.from_dict(d)
    expected = 'Unkown options in override_trunk/mid1: azertyop'
    with pytest.raises(ConfigError, match=expected) as e:
        opts.verify_all(cfg)
    print(e)


def test_verify_unknown_keys1():
    opts = gen_test_opts()
    d = {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "21",
                "leaf22": "22",
            },
            "mid3": "foobar",
        },
    }
    cfg = nc.ConfigNode.from_dict(d)
    expected = 'Unkown options in trunk: mid3'
    with pytest.raises(ConfigError, match=expected) as e:
        opts.verify_all(cfg)
    print(e)


def test_verify_unknown_keys2():
    opts = gen_test_opts()
    d = {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "21",
                "leaf22": "22",
                "foobar": 1234,
            },
        },
    }
    cfg = nc.ConfigNode.from_dict(d)
    expected = 'Unkown options in trunk/mid2: foobar'
    with pytest.raises(ConfigError, match=expected) as e:
        opts.verify_all(cfg)
    print(e)


def test_verify_wrong_type_str():
    opts = gen_test_opts()
    d = {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "21",
                "leaf22": 1234,
            },
        },
    }
    cfg = nc.ConfigNode.from_dict(d)
    expected = "Type of trunk/mid2/leaf22 should be <class 'str'>, " \
               "not <class 'int'>"
    with pytest.raises(ConfigError, match=expected) as e:
        opts.verify_all(cfg)
    print(e)


def test_verify_wrong_type_str_dict():
    opts = gen_test_opts()
    d = {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": {
                    "21": 1234
                },
            },
        },
    }
    cfg = nc.ConfigNode.from_dict(d)
    expected = "Type of trunk/mid2/leaf21 should be <class 'str'>, " \
               "not <class 'dict'>"
    with pytest.raises(ConfigError, match=expected) as e:
        opts.verify_all(cfg)
    print(e)


def test_inherit():
    opts = gen_test_opts()
    d = {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "21",
                "leaf22": "22",
            },
            "mid3": {},
        },
    }
    mid3 = opts[nc.pth('trunk')].insert(
        nc.ConfigOption('mid3', inherit_from=nc.pth('trunk/mid2')))

    cfg = nc.ConfigNode.from_dict(d)
    mid3.inherit(opts, cfg, nc.pth('trunk/mid3'))
    assert cfg.to_dict() == {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "21",
                "leaf22": "22",
            },
            "mid3": {
                "leaf21": "21",
                "leaf22": "22",
            },
        },
    }

    cfg = nc.ConfigNode.from_dict(d)
    cfg.setdefault(nc.pth('trunk/mid3/leaf22'), nc.ConfigNode(value="32"))
    mid3.inherit(opts, cfg, nc.pth('trunk/mid3'))
    assert cfg.to_dict() == {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "21",
                "leaf22": "22",
            },
            "mid3": {
                "leaf21": "21",
                "leaf22": "32",
            },
        },
    }


def test_config_node():
    d = {
        "trunk": {
            "mid1": {
                "leaf11": "11",
                "leaf12": "12",
            },
            "mid2": {
                "leaf21": "21",
                "leaf22": "22",
            },
        },
    }
    nodes = nc.ConfigNode.from_dict(d)
    for pth, val in nodes.iter_dfs():
        print(pth, val)
    assert nodes[nc.pth('')] is nodes
    assert nodes[nc.pth('')].value is None
    assert nodes[nc.pth('trunk')].value is None
    assert nodes[nc.pth('trunk/mid1')].value is None
    assert nodes[nc.pth('trunk/mid2')].value is None
    assert nodes[nc.pth('trunk/mid1/leaf11')].value == "11"
    assert nodes[nc.pth('trunk/mid1/leaf12')].value == "12"
    assert nodes[nc.pth('trunk/mid2/leaf21')].value == "21"
    assert nodes[nc.pth('trunk/mid2/leaf22')].value == "22"

    d2 = nodes.to_dict()
    assert d2 == d


def test_joinpth():
    assert nc.joinpth(nc.pth('a/b/c'), nc.pth('d/e')) == nc.pth('a/b/c/d/e')
    assert nc.joinpth(nc.pth('a/b/c'), nc.pth('^/e')) == nc.pth('a/b/e')
    assert nc.joinpth(nc.pth('a/b/c'), nc.pth('^/^/e')) == nc.pth('a/e')
    assert nc.joinpth(nc.pth('a/b/c'), nc.pth('^/^/^/e')) == nc.pth('e')
    assert nc.joinpth(nc.pth('a/b/c'), nc.pth('^/^/^/^/e')) == nc.pth('^/e')


def test_real_config_inherit_cross_cmake():
    opts = nc.get_options()
    d = {
        "pyproject.toml": {
            "tool": {
                "py-build-cmake": {
                    "cmake": {
                        "build_type": "Release",
                        "generator": "Ninja",
                        "env": {
                            "foo": "bar"
                        },
                        "args": ["arg1", "arg2"]
                    },
                    "cross": {
                        "implementation": "cp",
                        "version": "310",
                        "abi": "cp310",
                        "arch": "linux_aarch64",
                        "toolchain_file": "aarch64-linux-gnu.cmake",
                        "cmake": {
                            "generator": "Unix Makefiles",
                            "env": {
                                "crosscompiling": "true"
                            },
                            "args": ["arg3", "arg4"]
                        },
                    },
                }
            }
        }
    }
    cfg = nc.ConfigNode.from_dict(d)
    opts.verify_all(cfg)
    pprint(cfg.to_dict())
    opts.inherit_all(cfg)
    pprint(cfg.to_dict())
    assert cfg.to_dict() == {
        "pyproject.toml": {
            "tool": {
                "py-build-cmake": {
                    "cmake": {
                        "build_type": "Release",
                        "generator": "Ninja",
                        "env": {
                            "foo": "bar"
                        },
                        "args": ["arg1", "arg2"]
                    },
                    "cross": {
                        "implementation": "cp",
                        "version": "310",
                        "abi": "cp310",
                        "arch": "linux_aarch64",
                        "toolchain_file": "aarch64-linux-gnu.cmake",
                        "cmake": {
                            "build_type": "Release",
                            "generator": "Unix Makefiles",
                            "env": {
                                "foo": "bar",
                                "crosscompiling": "true",
                            },
                            "args": ["arg1", "arg2", "arg3", "arg4"]
                        },
                    },
                }
            }
        }
    }

    opts.update_default_all(cfg)
    # TODO: inherit default values as well 
    #       (but handle relative defaults correctly)
    pprint(cfg.to_dict())

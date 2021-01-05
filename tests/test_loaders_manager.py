from prettyconf.loaders import CommandLine, EnvFile, Environment, IniFile, Loaders


def test_basic_loaders_manager_default_loaders_in_order():
    manager = Loaders()
    assert len(manager.loaders) == 4
    assert isinstance(manager.loaders[0], CommandLine)
    assert isinstance(manager.loaders[1], Environment)
    assert isinstance(manager.loaders[2], EnvFile)
    assert isinstance(manager.loaders[3], IniFile)


def test_iterate_over_loaders():
    manager = Loaders()
    result = []
    for loader in manager.loaders:
        result.append(loader)

    assert len(result) == 4
    assert isinstance(result[0], CommandLine)
    assert isinstance(result[1], Environment)
    assert isinstance(result[2], EnvFile)
    assert isinstance(result[3], IniFile)
    # TODO: maybe add the 'deprecated' RecursiveLoader for backward compatibility?

import argparse
import copy
import os
import warnings
from configparser import ConfigParser, NoOptionError, NoSectionError
from typing import Callable, Optional, Type

try:
    import boto3
except ImportError:
    boto3 = None

try:
    import botocore
except ImportError:
    botocore = None

from .parsers import EnvFileParser
from .sources import FileSource, Source
from .exceptions import InvalidConfigurationFile, ParserError


class Loaders:
    def __init__(self, loaders=None):
        if loaders is None:
            loaders = [
                CommandLine(),
                Environment(),
                EnvFile(),
                IniFile(),
            ]
        self.loaders = loaders

    def get_config(self, key, source):
        for loader in self.loaders:
            try:
                return loader.get_config(key, source)
            except KeyError:
                continue
        else:
            raise KeyError(key)

    def __repr__(self):
        loaders = ', '.join(repr(loader) for loader in self.loaders)
        return f'Loaders([{loaders}])'


class NotSet(str):
    """
    A special type that behaves as a replacement for None.
    We have to put a new default value to know if a variable has been set by
    the user explicitly. This is useful for the ``CommandLine`` loader, when
    CLI parsers force you to set a default value, and thus, break the discovery
    chain.
    """

    pass


NOT_SET = NotSet()


def get_args(parser, args=None):
    """
    Converts arguments extracted from a parser to a dict,
    and will dismiss arguments which default to NOT_SET.

    :param parser: an ``argparse.ArgumentParser`` instance.
    :param args: list of arguments to be parsed. Use ``None`` to use sys.argv.
    :type parser: argparse.ArgumentParser
    :return: Dictionary with the configs found in the parsed CLI arguments.
    :rtype: dict
    """
    args, _ = parser.parse_known_args(args)
    args = vars(args).items()
    return {key: val for key, val in args if not isinstance(val, NotSet)}


class AbstractConfigurationLoader:
    source_type: Optional[Type[Source]] = None

    def __init__(self, source: Optional[Source] = None):
        if source is None and self.source_type is not None:
            source = self.source_type()
        self._source = source

    def get_config(self, key: str, source: Optional[Source] = None):
        if self.source_type and not isinstance(source, self.source_type):
            raise TypeError(f'Source is not a {self.source_type.__class__.__name__} instance')
        source = source or self._source
        return self._get_config(key, source)

    def _get_config(self, key, source):
        raise NotImplementedError()  # pragma: no cover

    def __repr__(self):
        raise NotImplementedError()  # pragma: no cover

    def __contains__(self, item):
        warnings.warn(
            'Loader.__contains__() usage will be deprecated. Check for Loader.get_config() KeyError exception instead',
            PendingDeprecationWarning,
        )
        try:
            return bool(self.get_config(item, self._source))
        except KeyError:
            return False

    def __getitem__(self, item):
        warnings.warn(
            'Loader.__getitem__() usage will be deprecated. Use .get_config() instead.',
            PendingDeprecationWarning,
        )
        return self.get_config(item, self._source)

    def check(self):
        warnings.warn(
            'Loader.check() usage will be deprecated.',
            PendingDeprecationWarning,
        )
        return True


# noinspection PyAbstractClass
class AbstractConfigurationFileLoader(AbstractConfigurationLoader):
    file_filters = ()


# TODO: Add a standard group for --config arguments like --config FOO=bar --config QUX=doo
def get_default_parser():
    parser = argparse.ArgumentParser()
    config_group = parser.add_argument_group('config')
    config_group.add_argument('--config', nargs='*', metavar='CONFIG=value', default=NOT_SET)
    return parser


class CommandLine(AbstractConfigurationLoader):
    """
    Extract configuration from an ``argparse`` parser.
    """

    def __init__(self, parser=None, get_args: Callable = get_args, args=None):
        """
        :param parser: An `argparse` parser instance to extract variables from.
        :param function get_args: A function to extract args from the parser.
        :type parser: argparse.ArgumentParser
        """
        super().__init__()

        if parser is None:
            parser = get_default_parser()

        self.parser = parser
        self.get_args = get_args
        self.args = args
        self.configs = {}

    # def _load(self, source: Optional = None):
    #     self.configs = self.get_args(self.parser, self.args)

    def _get_config(self, key, source):
        return self.configs[key]

    def __repr__(self):
        return 'CommandLine(parser={})'.format(self.parser)


class EnvFile(AbstractConfigurationLoader):
    source_type = FileSource
    file_extensions = ('.env',)

    def __init__(self,
                 filename='.env',
                 var_format: Callable = str.upper,
                 parser=None,
                 source=None):

        if filename and not source:
            warnings.warn('The use of filename will be deprecated. Use FileSource instead.', PendingDeprecationWarning)
            source = FileSource([filename])
        self._source = source

        super().__init__(source)

        if parser is None:
            parser = EnvFileParser()
        self.parser = parser

        self.var_format = var_format
        self.configs = {}

    def __repr__(self):
        return f'EnvFile({self._source!r})'

    def _load(self, source):
        for stream in source.get_streams():
            try:
                configs = self.parser.parse_config(stream)
            except ParserError:
                raise InvalidConfigurationFile(f'Error parsing {stream.name}')
            self.configs.update(configs)

    def _get_config(self, key, source):
        if not self.configs:
            self._load(source)

        return self.configs[self.var_format(key)]


class IniFile(AbstractConfigurationLoader):
    file_extensions = ('*.ini', '*.cfg')

    def __init__(self, filename='setup.cfg', section='settings', var_format: Callable = lambda x: x):
        """
        :param str filename: Path to the ``.ini/.cfg`` file.
        :param str section: Section name inside the config file.
        :param function var_format: A function to pre-format variable names.
        """
        super().__init__()
        self.filename = filename
        self.section = section
        self.var_format = var_format
        self.parser = ConfigParser(allow_no_value=True)
        self._initialized = False

    # def _load(self, source: Optional = None):
    # TODO: replace filename usage with source usage
    # with open(self.filename) as inifile:
    #     try:
    #         self.parser.read_file(inifile)
    #     except (UnicodeDecodeError, MissingSectionHeaderError):
    #         raise InvalidConfigurationFile()
    #
    # if not self.parser.has_section(self.section):
    #     raise MissingSettingsSection('Missing [{}] section in {}'.format(self.section, self.filename))
    #
    # self._initialized = True

    def __repr__(self):
        return "IniFile('{}')".format(self.filename)

    def _get_config(self, key, source):
        try:
            return self.parser.get(self.section, self.var_format(key))
        except (NoSectionError, NoOptionError):
            raise KeyError('{!r}'.format(key))


class Environment(AbstractConfigurationLoader):
    """
    Get's configuration from the environment, by inspecting ``os.environ``.
    """

    source_type = None

    def __init__(self, var_format: Callable = str.upper, source: Optional[Source] = None):
        """
        :param var_format: A function to pre-format variable names.
        :param source: an optional ``Source`` object
        """
        super().__init__(source)
        self.var_format = var_format
        self.configs = {}

    def _get_config(self, key, source):
        if not self.configs:
            self.configs = copy.copy(os.environ)

        key = self.var_format(key)
        return self.configs[key]

    def __repr__(self):
        return 'Environment(var_format={})'.format(self.var_format)


class AwsParameterStore(AbstractConfigurationLoader):
    def _load(self, source: Optional = None):
        # TODO: implement it
        pass

    def _get_config(self, key, source):
        # TODO: implement it
        pass

    def __init__(self, path='/', aws_access_key_id=None, aws_secret_access_key=None, region_name='us-east-1',
                 endpoint_url=None):
        super().__init__()
        if not boto3:
            raise RuntimeError(
                'AwsParameterStore requires [aws] feature. Please install it: pip install prettyconf[aws]'
            )

        self.path = path
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.region_name = region_name
        self.endpoint_url = endpoint_url
        self._fetched = False
        self._parameters = {}

    # TODO: refactor this loader to use new architecture
    def _store_parameters(self, parameters):
        for parameter in parameters:
            self._parameters[parameter['Name'].split('/')[-1]] = parameter['Value']

    def _fetch_parameters(self):
        if self._fetched:
            return

        client = boto3.client(
            service_name='ssm',
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region_name,
            endpoint_url=self.endpoint_url,
        )

        response = client.get_parameters_by_path(Path=self.path)
        next_token = response.get('NextToken')
        self._store_parameters(response['Parameters'])

        while next_token:
            response = client.get_parameters_by_path(Path=self.path, NextToken=next_token)
            next_token = response.get('NextToken')
            self._store_parameters(response['Parameters'])

        self._fetched = True

    def __repr__(self):
        return 'AwsParameterStore(path={} region={})'.format(self.path, self.region_name)


class RecursiveSearch(AbstractConfigurationLoader):
    def __init__(self, starting_path=None, filetypes=((".env", EnvFile), (("*.ini", "*.cfg"), IniFile)), root_path="/"):
        """
        :param str starting_path: The path to begin looking for configuration files.
        :param tuple filetypes: tuple of tuples with configuration loaders, order matters.
                                Defaults to
                                ``(('*.env', EnvFile), (('*.ini', *.cfg',), IniFile)``
        :param str root_path: Configuration lookup will stop at the given path. Defaults to
                              the current user directory
        """
        warnings.warn(
            'RecursiveSearchLoad will be deprecated. '
            'Use the new RecursiveFileSearchSource() with the proper loader instead.',
            PendingDeprecationWarning,
        )
        self.root_path = os.path.realpath(root_path)
        self._starting_path = self.root_path

        if starting_path:
            self.starting_path = starting_path

        self.filetypes = filetypes
        self._config_files = None
    #
    # @property
    # def starting_path(self):
    #     return self._starting_path
    #
    # @starting_path.setter
    # def starting_path(self, path):
    #     if not path:
    #         raise InvalidPath("Invalid starting path")
    #
    #     path = os.path.realpath(os.path.abspath(path))
    #     if not path.startswith(self.root_path):
    #         raise InvalidPath("Invalid root path given")
    #     self._starting_path = path
    #
    # @staticmethod
    # def get_filenames(path, patterns):
    #     filenames = []
    #     if type(patterns) is str:
    #         patterns = (patterns,)
    #
    #     for pattern in patterns:
    #         filenames += glob(os.path.join(path, pattern))
    #     return filenames
    #
    # def _scan_path(self, path):
    #     config_files = []
    #
    #     for patterns, Loader in self.filetypes:
    #         for filename in self.get_filenames(path, patterns):
    #             try:
    #                 loader = Loader(filename=filename)
    #                 if not loader.check():
    #                     continue
    #                 config_files.append(loader)
    #             except InvalidConfigurationFile:
    #                 continue
    #
    #     return config_files
    #
    # def _discover(self):
    #     self._config_files = []
    #
    #     path = self.starting_path
    #     while True:
    #         if os.path.isdir(path):
    #             self._config_files += self._scan_path(path)
    #
    #         if path == self.root_path:
    #             break
    #
    #         path = os.path.dirname(path)
    #
    # @property
    # def config_files(self):
    #     if self._config_files is None:
    #         self._discover()
    #
    #     return self._config_files
    #
    # def __repr__(self):
    #     return "RecursiveSearch(starting_path={})".format(self.starting_path)
    #
    # def __contains__(self, item):
    #     for config_file in self.config_files:
    #         if item in config_file:
    #             return True
    #     return False
    #
    # def __getitem__(self, item):
    #     for config_file in self.config_files:
    #         try:
    #             return config_file[item]
    #         except KeyError:
    #             continue
    #     else:
    #         raise KeyError("{!r}".format(item))

import ast
import warnings

from .casts import Boolean, JSON, List, Option, Tuple
from .exceptions import UnknownConfiguration
from .loaders import Loaders


class Configuration(object):
    # Shortcut for standard casts
    boolean = Boolean()
    list = List()
    tuple = Tuple()
    option = Option
    eval = staticmethod(ast.literal_eval)
    json = JSON()

    def __init__(self, loaders=None):
        if not isinstance(loaders, Loaders):
            loaders = Loaders(loaders)
        self.loaders_manager = loaders

    @property
    def loaders(self):
        warnings.warn(
            'This property will be deprecated soon. Use self.load_manager.loaders instead',
            PendingDeprecationWarning,
        )
        return self.loaders_manager.loaders

    def __repr__(self):
        loaders = ', '.join([repr(loader) for loader in self.loaders_manager.loaders])
        return '{}(loaders=[{}])'.format(self.__class__.__name__, loaders)

    def __call__(self, item, cast=lambda v: v, source=None, **kwargs):
        if not callable(cast):
            raise TypeError("Cast must be callable")

        try:
            config = self.loaders_manager.get_config(item, source)
        except KeyError:
            config = kwargs.get('default')

        if config is None:
            raise UnknownConfiguration(f"Configuration '{item}' not found")

        return cast(config)

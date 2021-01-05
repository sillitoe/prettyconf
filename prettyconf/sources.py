import os
import sys
from glob import glob
from typing import List, TextIO

from .exceptions import FileNotFound, InvalidPath

MAGIC_FRAME_DEPTH = 2


def caller_path(depth=MAGIC_FRAME_DEPTH):
    # MAGIC! Get the caller's module path.
    # noinspection PyProtectedMember,PyUnresolvedReferences
    frame = sys._getframe(depth)
    path = os.path.dirname(os.path.abspath(frame.f_code.co_filename))
    return path


class MagicStartPath:
    def __str__(self):
        return ''  # TODO: implement caller_path logic here


class Source:
    @property
    def filenames(self) -> List[str]:
        raise NotImplementedError()  # pragma: nocover

    def get_streams(self) -> List[TextIO]:
        raise NotImplementedError()  # pragma: nocover


class FileSource(Source):
    def __init__(self, filenames):
        self._filenames = filenames

    @property
    def filenames(self):
        return self._filenames

    def get_streams(self):
        for filename in self.filenames:
            try:
                with open(filename, 'r') as source:
                    yield source
            except FileNotFoundError:
                continue

    def __repr__(self):
        return repr(self.filenames)


class RecursiveFileSearchSource(Source):
    def __init__(self, patterns=None, start_path=None, root_path='/'):
        if patterns is None:
            patterns = []
        self.patterns = patterns

        if start_path is None:
            start_path = MagicStartPath()
        self._start_path = start_path

        self.root_path = os.path.realpath(root_path)

    @property
    def start_path(self):
        return self._start_path

    @start_path.setter
    def start_path(self, path):
        if not path:
            raise InvalidPath('Invalid starting path')

        path = os.path.realpath(os.path.abspath(path))
        if not path.startswith(self.root_path):
            raise InvalidPath('Invalid root path given')
        if not os.path.exists(path):
            raise InvalidPath('Invalid starting path')
        if not os.path.isdir(path):
            path = os.path.dirname(path)

        self._start_path = path

    @property
    def filenames(self) -> List[str]:
        if not self.start_path:
            self.start_path = caller_path(MAGIC_FRAME_DEPTH)
        return []

    def reset(self):
        pass  # TODO

    def find_first(self, patterns):
        for filename in self.find_all(patterns):
            return filename
        else:
            raise FileNotFound(r'Cannot find one file with the patterns {patterns}')

    def find_all(self, patterns):
        patterns = set(patterns)

        start_path = self.starting_path
        while start_path != self.root_path:
            for pattern in patterns:
                path = os.path.join(start_path, pattern)
                for filename in glob(path):
                    yield filename

            start_path = os.path.dirname(start_path)  # up!

    def __repr__(self):
        return f'RecursiveFileSearchSource(patterns={self.patterns!r}, start_path={self.start_path}'

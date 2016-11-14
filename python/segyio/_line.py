import itertools

import segyio


class Line:
    """ Line mode for traces and trace headers. Internal.

    The _line class provides an interface for line-oriented operations. The
    line reading operations themselves are not streaming - it's assumed than
    when a line is queried it's somewhat limited in size and will comfortably
    fit in memory, and that the full line is interesting. This also applies to
    line headers; however, all returned values support the iterable protocol so
    they work fine together with the streaming bits of this library.

    _line should not be instantiated directly by users, but rather returned
    from the iline/xline properties of file or from the header mode. Any
    direct construction of this should be considered an error.
    """

    def __init__(self, segy, length, stride, lines, other_lines, buffn, readfn, writefn, name):
        self.segy = segy
        self.len = length
        self.stride = stride
        self.lines = lines
        self.other_lines = other_lines
        self.name = name
        self.buffn = buffn
        self.readfn = readfn
        self.writefn = writefn

    def _get(self, lineno, offset, buf):
        """ :rtype: numpy.ndarray"""

        offs = self.segy.offsets

        if offset is None:
            offset = 0
        else:
            try:
                offset = next(i for i, x in enumerate(offs) if x == offset)
            except StopIteration:
                try:
                    int(offset)
                except TypeError:
                    raise TypeError("Offset must be int or slice")

                raise KeyError("Unknkown offset {}".format(offset))

        try:
            lineno = int(lineno)
        except TypeError:
            raise TypeError("Must be int or slice")

        t0 = self.trace0fn(lineno, offset)
        return self.readfn(t0, self.len, self.stride, buf)

    # in order to support [:end] syntax, we must make sure
    # start has a non-None value. lineno.indices() would set it
    # to 0, but we don't know if that's a reasonable value or
    # not. If start is None we set it to the first line
    def _sanitize_slice(self, s, source):
        if all((s.start, s.stop, s.step)):
            return s

        start, stop, step = s.start, s.stop, s.step
        increasing = step is None or step > 0

        if start is None:
            start = source[0] if increasing else source[-1]

        if stop is None:
            stop = source[-1]+1 if increasing else source[0]-1

        return slice(start, stop, step)

    def _get_iter(self, lineno, offset, buf):
        """ :rtype: collections.Iterable[numpy.ndarray]"""

        offsets = self.segy.offsets
        if offset is None:
            offset = offsets[0]

        if not isinstance(lineno, slice):
            lineno = slice(lineno, lineno + 1, 1)

        if not isinstance(offset, slice):
            offset = slice(offset, offset + 1, 1)

        lineno = self._sanitize_slice(lineno, self.lines)
        offset = self._sanitize_slice(offset, offsets)

        def gen():
            offs, lns = set(self.segy.offsets), set(self.lines)
            orng = xrange(*offset.indices(offsets[-1] + 1))
            lrng = xrange(*lineno.indices(self.lines[-1] + 1))

            for l in itertools.ifilter(lns.__contains__, lrng):
                for o in itertools.ifilter(offs.__contains__, orng):
                    yield self._get(l, o, buf)

        return gen()

    def __getitem__(self, lineno, offset = None):
        """ :rtype: numpy.ndarray|collections.Iterable[numpy.ndarray]"""
        buf = self.buffn()

        if isinstance(lineno, tuple):
            lineno, offset = lineno

        if isinstance(lineno, slice) or isinstance(offset, slice):
            return self._get_iter(lineno, offset, buf)

        return self._get(lineno, offset, buf)

    def trace0fn(self, lineno, offset_index):
        offsets = len(self.segy.offsets)
        trace0 = segyio._segyio.fread_trace0(lineno, len(self.other_lines), self.stride, offsets, self.lines, self.name)
        return offset_index + trace0

    def __setitem__(self, lineno, val):
        if isinstance(lineno, slice):
            if lineno.start is None:
                lineno = slice(self.lines[0], lineno.stop, lineno.step)

            rng = range(*lineno.indices(self.lines[-1] + 1))
            s = set(self.lines)

            for i, x in itertools.izip(filter(s.__contains__, rng), val):
                self.__setitem__(i, x)

            return

        t0 = self.trace0fn(lineno, 0)
        self.writefn(t0, self.len, self.stride, val)

    def __len__(self):
        return len(self.lines)

    def __iter__(self):
        buf = self.buffn()
        for i in self.lines:
            yield self._get(i, None, buf)

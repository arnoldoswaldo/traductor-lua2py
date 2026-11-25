import bisect as _bisect
import gc as _gc
import weakref as _weakref
import builtins as _builtins
import keyword as _keyword
import math as _math
import os as _pyos
import random as _random
import re as _re
import sys as _sys
import threading as _threading
import time as _time
from functools import cmp_to_key as _cmp_to_key

if _sys.version_info >= (3, 11):
    _sys.setrecursionlimit(150000)
else:
    _sys.setrecursionlimit(7000)

_MAXI = 9223372036854775807
_MINI = -9223372036854775808

def _out(text):
    _sys.stdout.buffer.write(text.encode("latin-1", "replace"))

_TRUE_KEY = object()
_FALSE_KEY = object()

class LuaError(Exception):

    def __init__(self, value=None):
        Exception.__init__(self, value)
        self.value = value

_THIS_FILE = _sys._getframe().f_code.co_filename

def _user_lines(frame):
    start = globals().get("_USER_START")
    keys = globals().get("_LINEKEYS")
    lines = []
    if not start or not keys:
        return lines
    while frame is not None:
        if frame.f_code.co_filename == _THIS_FILE:
            if frame.f_lineno > start:
                index = _bisect.bisect_right(keys, frame.f_lineno) - 1
                if index >= 0:
                    lines.append(_LINEMAP[keys[index]])
            elif frame.f_code.co_name in ("lua_pcall", "lua_xpcall"):
                lines.append(None)
        frame = frame.f_back
    return lines

def _pos(level=1):
    lines = _user_lines(_sys._getframe(1))
    if level < 1 or level > len(lines) or lines[level - 1] is None:
        return ""
    return "%s:%d: " % (globals().get("_CHUNK", "input"), lines[level - 1])

def _err(message, level=1):
    return LuaError(_pos(level) + message)

def _name_hint(kind, line):
    info = globals().get("_DEBUG", {}).get(line)
    if not info:
        return ""
    kept = set()
    for desc, pyname in info.get(kind, []):
        if pyname is not None:
            value = globals().get(pyname)
            if kind == "call" and callable(value):
                continue
            if kind == "index" and isinstance(value, (LuaTable, str)):
                continue
        kept.add(desc)
    return " (%s)" % kept.pop() if len(kept) == 1 else ""

def _exc_message(exc):
    if isinstance(exc, LuaError):
        return exc.value
    names = {"NoneType": "nil", "int": "number", "float": "number", "str": "string",
             "bool": "boolean", "LuaTable": "table", "function": "function"}
    text = str(exc)
    cmp_match = _re.match(r"'([<>]=?)' not supported between instances of '(\w+)' and '(\w+)'", text)
    if "does not support item assignment" in text:
        text = text.replace("does not support item assignment", "is not subscriptable")
    match = _re.match(r"'(\w+)' object is not (callable|subscriptable)", text)
    if cmp_match:
        left, right = names.get(cmp_match.group(2), cmp_match.group(2)), \
            names.get(cmp_match.group(3), cmp_match.group(3))
        if cmp_match.group(1).startswith(">"):
            left, right = right, left
        text = ("attempt to compare two %s values" % left if left == right
                else "attempt to compare %s with %s" % (left, right))
    elif match:
        kind = names.get(match.group(1), match.group(1))
        what = "call" if match.group(2) == "callable" else "index"
        text = "attempt to %s a %s value" % (what, kind)
    elif isinstance(exc, RecursionError):
        text = "stack overflow"
    lines = []
    trace = exc.__traceback__
    while trace is not None:
        if trace.tb_frame.f_code.co_filename == _THIS_FILE:
            lines.append(trace.tb_frame.f_lineno)
        trace = trace.tb_next
    start = globals().get("_USER_START")
    keys = globals().get("_LINEKEYS")
    for lineno in reversed(lines):
        if start and keys and lineno > start:
            index = _bisect.bisect_right(keys, lineno) - 1
            if index >= 0:
                lua_line = _LINEMAP[keys[index]]
                if text.startswith("attempt to call"):
                    text += _name_hint("call", lua_line)
                elif text.startswith("attempt to index"):
                    text += _name_hint("index", lua_line)
                return "%s:%d: %s" % (globals().get("_CHUNK", "input"), lua_line, text)
    return text

class LuaGoto(Exception):

    def __init__(self, label):
        Exception.__init__(self, label)
        self.label = label

def _metamethod(value, event):
    if isinstance(value, LuaTable) and value.meta is not None:
        return value.meta.hash.get(event)
    return None

def _normkey(key):
    if key is True:
        return _TRUE_KEY
    if key is False:
        return _FALSE_KEY
    if isinstance(key, float) and key.is_integer():
        return int(key)
    return key

def _denormkey(key):
    if key is _TRUE_KEY:
        return True
    if key is _FALSE_KEY:
        return False
    return key

class LuaTable(object):

    __slots__ = ("arr", "hash", "meta", "__weakref__")

    def __init__(self):
        self.arr = []
        self.hash = {}
        self.meta = None

    def length(self):
        return len(self.arr)

    def __getitem__(self, key):
        key = _normkey(key)
        if type(key) is int and 1 <= key <= len(self.arr):
            value = self.arr[key - 1]
        else:
            value = self.hash.get(key)
        if value is None and self.meta is not None:
            return self._meta_index(_denormkey(key))
        return value

    def _meta_index(self, key):
        handler = self.meta.hash.get("__index")
        if handler is None:
            return None
        if isinstance(handler, LuaTable):
            return handler[key]
        return lua_first(handler(self, key))

    def rawget(self, key):
        key = _normkey(key)
        if type(key) is int and 1 <= key <= len(self.arr):
            return self.arr[key - 1]
        return self.hash.get(key)

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        if self is other:
            return True
        if isinstance(other, LuaTable):
            handler = _metamethod(self, "__eq") or _metamethod(other, "__eq")
            if handler is not None:
                return lua_truth(lua_first(handler(self, other)))
        return False

    def __lt__(self, other):
        return _compare_meta(self, other, "__lt")

    def __le__(self, other):
        return _compare_meta(self, other, "__le")

    def __gt__(self, other):
        return _compare_meta(other, self, "__lt")

    def __ge__(self, other):
        return _compare_meta(other, self, "__le")

    def __setitem__(self, key, value):
        if self.meta is not None:
            handler = self.meta.hash.get("__newindex")
            if handler is not None and self.rawget(key) is None:
                if isinstance(handler, LuaTable):
                    handler[key] = value
                else:
                    handler(self, key, value)
                return
        self.rawset(key, value)

    def rawset(self, key, value):
        key = _normkey(key)
        if key is None:
            raise LuaError("index is nil")
        if type(key) is int:
            n = len(self.arr)
            if 1 <= key <= n:
                if value is not None:
                    self.arr[key - 1] = value
                elif key == n:
                    self.arr.pop()
                else:
                    tail = self.arr[key:]
                    del self.arr[key - 1:]
                    for offset, item in enumerate(tail, key + 1):
                        self.hash[offset] = item
                return
            if key == n + 1:
                if value is None:
                    self.hash.pop(key, None)
                    return
                self.arr.append(value)
                self.hash.pop(key, None)
                nxt = key + 1
                while nxt in self.hash:
                    self.arr.append(self.hash.pop(nxt))
                    nxt += 1
                return
        if value is None:
            self.hash.pop(key, None)
        else:
            self.hash[key] = value

    def __call__(self, *args):
        handler = self.meta.hash.get("__call") if self.meta is not None else None
        if handler is None:
            raise _err("attempt to call a table value")
        return handler(self, *args)

def lua_table(positional=(), keyed=()):
    table = LuaTable()
    for key, value in keyed:
        table[key] = value
    for index, value in enumerate(positional, 1):
        table.rawset(index, value)
    return table

def _compare_meta(left, right, event):
    handler = _metamethod(left, event) or _metamethod(right, event)
    if handler is None:
        if type_(left) == type_(right):
            raise _err("attempt to compare two %s values" % type_(left))
        raise _err("attempt to compare %s with %s" % (type_(left), type_(right)))
    return lua_truth(lua_first(handler(left, right)))

def lua_multi(result):
    return result if isinstance(result, tuple) else (result,)

def lua_first(result):
    if isinstance(result, tuple):
        return result[0] if result else None
    return result

def lua_adjust(result, count):
    values = lua_multi(result)
    if len(values) >= count:
        return values[:count]
    return values + (None,) * (count - len(values))

def lua_tostring(value):
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float):
        if value != value:
            return "-nan" if _math.copysign(1.0, value) < 0 else "nan"
        if value in (float("inf"), float("-inf")):
            return "inf" if value > 0 else "-inf"
        text = "%.14g" % value
        if float(text) != value:
            text = "%.17g" % value
        if all(ch in "-0123456789" for ch in text):
            text += ".0"
        return text
    if isinstance(value, LuaTable):
        handler = _metamethod(value, "__tostring")
        if handler is not None:
            return lua_tostring(lua_first(handler(value)))
        return "table: 0x%08x" % id(value)
    if isinstance(value, LuaCoroutine):
        return "thread: 0x%08x" % id(value)
    if isinstance(value, LuaFile):
        return "file (0x%08x)" % id(value)
    if callable(value):
        return "function: 0x%08x" % id(value)
    return str(value)


def lua_tonumber(value, base=None):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if base is not None:
        try:
            return int(text, int(base))
        except ValueError:
            return None
    if not text or "_" in text:
        return None
    try:
        if text.lower().lstrip("+-").startswith("0x"):
            return int(text, 16)
        return int(text)
    except ValueError:
        pass
    if text.lower().lstrip("+-") in ("nan", "inf", "infinity"):
        return None
    try:
        return float(text)
    except ValueError:
        return None

def type_(value):
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, LuaTable):
        return "table"
    if isinstance(value, LuaCoroutine):
        return "thread"
    if isinstance(value, LuaFile):
        return "userdata"
    return "function"

def lua_print(*args):
    _out("\t".join(lua_tostring(a) for a in args) + "\n")

def lua_len(value):
    if isinstance(value, str):
        return len(value)
    if isinstance(value, LuaTable):
        handler = _metamethod(value, "__len")
        if handler is not None:
            return lua_first(handler(value))
        return value.length()
    raise _err("attempt to get length of a %s value" % type_(value))

def lua_truth(value):
    return value is not None and value is not False

def lua_range(start, stop, step=1):
    if step == 0:
        raise LuaError("'for' step is zero")
    if all(isinstance(v, int) and not isinstance(v, bool)
           for v in (start, stop, step)):
        return range(start, stop + 1 if step > 0 else stop - 1, step)
    return _float_range(start, stop, step)

def _float_range(start, stop, step):
    current = start
    if step > 0:
        while current <= stop:
            yield current
            current += step
    else:
        while current >= stop:
            yield current
            current += step

class _LuaIter(object):

    __slots__ = ("gen",)

    def __init__(self, gen):
        self.gen = gen

def lua_pairs(table):
    if not isinstance(table, LuaTable):
        raise _err("bad argument #1 to 'for iterator' (table expected, got %s)"
                       % type_(table))

    def gen():
        for index, value in enumerate(list(table.arr), 1):
            if value is not None:
                yield (index, value)
        for key, value in list(table.hash.items()):
            yield (_denormkey(key), value)
    return _LuaIter(gen())

def lua_ipairs(table):
    def gen():
        index = 1
        while True:
            value = table[index]
            if value is None:
                return
            yield (index, value)
            index += 1
    return _LuaIter(gen())

def lua_for(count, first=None, state=None, control=None):
    if isinstance(first, _LuaIter):
        for item in first.gen:
            yield lua_adjust(item, count)
        return
    if first is None:
        raise _err("attempt to call a nil value")
    while True:
        values = lua_adjust(first(state, control), count)
        if values[0] is None:
            return
        control = values[0]
        yield values

def lua_callm(obj, name, *args):
    method = _string_lib[name] if isinstance(obj, str) else obj[name]
    if method is None:
        raise _err("attempt to call a nil value (method '%s')" % name)
    return method(obj, *args)

def lua_error(message=None, level=1):
    if message is None:
        raise LuaError("<no error object>")
    if type(message) is str and level is not None and level > 0:
        raise LuaError(_pos(int(level)) + message)
    raise LuaError(message)

def lua_assert(value=None, message=None, *rest):
    if lua_truth(value):
        return (value, message) + rest if (message is not None or rest) else value
    if message is None:
        message = "assertion failed!"
    if type(message) is str:
        raise LuaError(_pos(1) + message)
    raise LuaError(message)

def lua_pcall(func, *args):
    try:
        return (True,) + lua_multi(func(*args))
    except LuaError as exc:
        return (False, exc.value)
    except RecursionError:
        return (False, "stack overflow")
    except Exception as exc:
        return (False, str(exc))

def lua_select(selector, *args):
    if selector == "#":
        return len(args)
    selector = int(selector)
    if selector < 0:
        selector = len(args) + selector + 1
    return args[selector - 1:]

_weak_tables = _weakref.WeakSet()

def lua_setmetatable(table, meta):
    table.meta = meta
    if meta is not None and isinstance(meta.hash.get("__mode"), str):
        _weak_tables.add(table)
    return table

def lua_getmetatable(table):
    return table.meta if isinstance(table, LuaTable) else None

_FMT = _re.compile(r"%([-+ #0]*)(\d+)?(?:\.(\d+))?([a-zA-Z%])")

def _str_format(fmt, *args):
    values = list(args)
    pos = [0]

    def repl(match):
        flags, width, prec, conv = match.groups()
        if conv == "%":
            return "%"
        if pos[0] >= len(values):
            raise _err("bad argument #%d to 'format' (no value)" % (pos[0] + 2))
        value = values[pos[0]]
        pos[0] += 1
        spec = "%" + flags + (width or "") + ("." + prec if prec is not None else "")
        if conv in "diu":
            if isinstance(value, str):
                value = lua_tonumber(value)
            if isinstance(value, float):
                if not value.is_integer():
                    raise _err("bad argument to 'format' (number has no integer representation)")
                value = int(value)
            return (spec + "d") % value
        if conv in "xXo":
            return (spec + conv) % int(value)
        if conv == "c":
            return chr(int(value))
        if conv in "eEfFgG":
            return (spec + conv) % float(value)
        if conv == "s":
            return (spec + "s") % lua_tostring(value)
        if conv == "q":
            text = lua_tostring(value)
            body = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\\n")
            return '"' + body.replace("\r", "\\r").replace("\0", "\\0") + '"'
        raise LuaError("invalid conversion '%%%s' to 'format'" % conv)
    return _FMT.sub(repl, fmt)

def _str_sub(text, i=1, j=-1):
    n = len(text)
    i, j = int(i), int(j)
    if i < 0:
        i = max(n + i + 1, 1)
    elif i == 0:
        i = 1
    if j < 0:
        j = n + j + 1
    elif j > n:
        j = n
    return "" if i > j else text[i - 1:j]

def _str_rep(text, count, sep=""):
    count = int(count)
    return sep.join([text] * count) if count > 0 else ""

def _str_byte(text, i=1, j=None):
    j = i if j is None else j
    sub = _str_sub(text, i, j)
    codes = tuple(ord(ch) for ch in sub)
    return codes if len(codes) != 1 else codes[0]

def _make_lib(entries):
    lib = LuaTable()
    for name, value in entries.items():
        lib[name] = value
    return lib

_string_lib = _make_lib({
    "len": len, "sub": _str_sub, "upper": lambda s: s.upper(),
    "lower": lambda s: s.lower(), "rep": _str_rep, "reverse": lambda s: s[::-1],
    "byte": _str_byte, "char": lambda *c: "".join(chr(int(x)) for x in c),
    "format": _str_format,
})
string = _string_lib

def _tbl_insert(table, *args):
    if len(args) == 1:
        table[table.length() + 1] = args[0]
        return
    pos, value = int(args[0]), args[1]
    n = table.length()
    if pos < 1 or pos > n + 1:
        raise _err("bad argument #2 to 'insert' (position out of bounds)")
    table.arr.insert(pos - 1, value)

def _tbl_remove(table, pos=None):
    n = table.length()
    if pos is None:
        pos = n
    pos = int(pos)
    if n == 0 and pos in (0, n):
        return None
    if pos < 1 or pos > n + 1:
        raise _err("bad argument #2 to 'remove' (position out of bounds)")
    if pos == n + 1:
        return None
    return table.arr.pop(pos - 1)

def _tbl_concat(table, sep="", i=1, j=None):
    j = table.length() if j is None else int(j)
    return sep.join(lua_tostring(table[k]) for k in range(int(i), j + 1))

def _tbl_unpack(table, i=1, j=None):
    j = table.length() if j is None else int(j)
    return tuple(table[k] for k in range(int(i), j + 1))

def _tbl_sort(table, comp=None):
    if comp is None:
        table.arr.sort()
        return

    def compare(a, b):
        if lua_truth(lua_first(comp(a, b))):
            return -1
        return 1 if lua_truth(lua_first(comp(b, a))) else 0
    table.arr.sort(key=_cmp_to_key(compare))

_table_lib = _make_lib({
    "insert": _tbl_insert, "remove": _tbl_remove, "concat": _tbl_concat,
    "unpack": _tbl_unpack, "sort": _tbl_sort,
})
table = _table_lib

def _m_floor(x):
    try:
        return _math.floor(x)
    except (OverflowError, ValueError):
        return x

def _m_ceil(x):
    try:
        return _math.ceil(x)
    except (OverflowError, ValueError):
        return x

def _m_random(m=None, n=None):
    if m is None:
        return _random.random()
    if n is None:
        return _random.randint(1, int(m))
    return _random.randint(int(m), int(n))

def _m_tointeger(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return None

def _m_type(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return "integer" if isinstance(x, int) else "float"

def _m_log(x, base=None):
    if base is None:
        return _math.log(x)
    return _math.log(x, base)

_math_lib = _make_lib({
    "floor": _m_floor, "ceil": _m_ceil, "sqrt": lambda x: _math.sqrt(x),
    "abs": abs, "max": max, "min": min, "huge": float("inf"), "pi": _math.pi,
    "random": _m_random, "randomseed": lambda *a: _random.seed(*a),
    "fmod": lambda a, b: _math.fmod(a, b), "tointeger": _m_tointeger,
    "type": _m_type, "sin": _math.sin, "cos": _math.cos, "tan": _math.tan,
    "exp": _math.exp, "log": _m_log,
    "maxinteger": 9223372036854775807, "mininteger": -9223372036854775808,
})
math = _math_lib

def _io_write(*args):
    for item in args:
        _sys.stdout.write(lua_tostring(item))

_os_lib = _make_lib({
    "time": lambda *a: int(_time.time()), "clock": lambda: _time.process_time(),
    "exit": lambda code=0: _sys.exit(0 if code in (None, True) else int(code or 0)),
})
os = _os_lib
_io_lib = _make_lib({"write": _io_write})
io = _io_lib

def _wrap(value):
    return ((value + 9223372036854775808) & 0xFFFFFFFFFFFFFFFF) - 9223372036854775808

def _tonum(value):
    kind = type(value)
    if kind is int or kind is float:
        return value
    if kind is str:
        return lua_tonumber(value)
    return None

def _arith(event, left, right, func):
    handler = _metamethod(left, event) or _metamethod(right, event)
    if handler is not None:
        return lua_first(handler(left, right))
    x, y = _tonum(left), _tonum(right)
    if x is None or y is None:
        bad = right if x is not None else left
        raise _err("attempt to perform arithmetic on a %s value" % type_(bad))
    return func(x, y)

def lua_add(a, b):
    ta, tb = type(a), type(b)
    if ta is int and tb is int:
        r = a + b
        return r if _MINI <= r <= _MAXI else _wrap(r)
    if (ta is float or ta is int) and (tb is float or tb is int):
        return a + b
    return _arith("__add", a, b, lua_add)

def lua_sub(a, b):
    ta, tb = type(a), type(b)
    if ta is int and tb is int:
        r = a - b
        return r if _MINI <= r <= _MAXI else _wrap(r)
    if (ta is float or ta is int) and (tb is float or tb is int):
        return a - b
    return _arith("__sub", a, b, lua_sub)

def lua_mul(a, b):
    ta, tb = type(a), type(b)
    if ta is int and tb is int:
        r = a * b
        return r if _MINI <= r <= _MAXI else _wrap(r)
    if (ta is float or ta is int) and (tb is float or tb is int):
        return a * b
    return _arith("__mul", a, b, lua_mul)

def lua_div(a, b):
    ta, tb = type(a), type(b)
    if (ta is float or ta is int) and (tb is float or tb is int):
        try:
            return float(a) / b
        except ZeroDivisionError:
            if a == 0 or a != a:
                return -float("nan")
            positive = (a > 0) == (_math.copysign(1.0, b) > 0)
            return float("inf") if positive else float("-inf")
    return _arith("__div", a, b, lua_div)

def lua_mod(a, b):
    ta, tb = type(a), type(b)
    if ta is int and tb is int:
        if b == 0:
            raise _err("attempt to perform 'n%0'")
        return a % b
    if (ta is float or ta is int) and (tb is float or tb is int):
        try:
            m = _math.fmod(a, b)
        except (ValueError, ZeroDivisionError):
            return float("nan")
        if m != 0 and (m < 0) != (b < 0):
            m += b
        return m
    return _arith("__mod", a, b, lua_mod)

def lua_idiv(a, b):
    ta, tb = type(a), type(b)
    if ta is int and tb is int:
        if b == 0:
            raise _err("attempt to divide by zero")
        r = a // b
        return r if r <= _MAXI else _wrap(r)
    if (ta is float or ta is int) and (tb is float or tb is int):
        try:
            return float(a // b)
        except ZeroDivisionError:
            return lua_div(a, b)
    return _arith("__idiv", a, b, lua_idiv)

def lua_pow(a, b):
    ta, tb = type(a), type(b)
    if (ta is float or ta is int) and (tb is float or tb is int):
        try:
            return _math.pow(a, b)
        except OverflowError:
            return float("inf")
        except ValueError:
            if a == 0:
                return float("inf")
            return -float("nan")
    return _arith("__pow", a, b, lua_pow)

def lua_unm(a):
    ta = type(a)
    if ta is int:
        return -a if a != _MINI else a
    if ta is float:
        return -a
    handler = _metamethod(a, "__unm")
    if handler is not None:
        return lua_first(handler(a, a))
    x = _tonum(a)
    if x is None:
        raise _err("attempt to perform arithmetic on a %s value" % type_(a))
    return lua_unm(x)

def lua_concat(a, b):
    ta, tb = type(a), type(b)
    if ta is str and tb is str:
        return a + b
    if ta in (str, int, float) and tb in (str, int, float):
        return lua_tostring(a) + lua_tostring(b)
    handler = _metamethod(a, "__concat") or _metamethod(b, "__concat")
    if handler is not None:
        return lua_first(handler(a, b))
    bad = b if ta in (str, int, float) else a
    raise _err("attempt to concatenate a %s value" % type_(bad))

def lua_eq(a, b):
    if type(a) is bool or type(b) is bool:
        return a is b
    return a == b

def _toint(value):
    kind = type(value)
    if kind is int:
        return value
    if kind is float:
        if value == value and abs(value) < 9.3e18 and value.is_integer():
            return int(value)
        return None
    return None

def _bitop(event, a, b, func):
    handler = _metamethod(a, event) or _metamethod(b, event)
    if handler is not None:
        return lua_first(handler(a, b))
    x, y = _toint(a), _toint(b)
    if x is None or y is None:
        bad = b if x is not None else a
        if _tonum(bad) is not None:
            raise _err("number has no integer representation")
        raise _err("attempt to perform bitwise operation on a %s value" % type_(bad))
    return func(x, y)

def _shift_left(x, n):
    if n <= -64 or n >= 64:
        return 0
    if n >= 0:
        return _wrap((x & 0xFFFFFFFFFFFFFFFF) << n)
    return _wrap((x & 0xFFFFFFFFFFFFFFFF) >> -n)

def lua_band(a, b):
    return _bitop("__band", a, b, lambda x, y: x & y)

def lua_bor(a, b):
    return _bitop("__bor", a, b, lambda x, y: x | y)

def lua_bxor(a, b):
    return _bitop("__bxor", a, b, lambda x, y: x ^ y)

def lua_shl(a, b):
    return _bitop("__shl", a, b, _shift_left)


def lua_shr(a, b):
    return _bitop("__shr", a, b, lambda x, y: _shift_left(x, -y))

def lua_bnot(a):
    handler = _metamethod(a, "__bnot")
    if handler is not None:
        return lua_first(handler(a, a))
    x = _toint(a)
    if x is None:
        raise _err("attempt to perform bitwise operation on a %s value" % type_(a))
    return ~x

def lua_next(table, key=None):
    if key is None:
        for index, value in enumerate(table.arr, 1):
            if value is not None:
                return (index, value)
        for k, v in table.hash.items():
            return (_denormkey(k), v)
        return None
    key = _normkey(key)
    arr = table.arr
    if type(key) is int and 1 <= key <= len(arr):
        for index in range(key, len(arr)):
            if arr[index] is not None:
                return (index + 1, arr[index])
        for k, v in table.hash.items():
            return (_denormkey(k), v)
        return None
    keys = list(table.hash)
    try:
        pos = keys.index(key)
    except ValueError:
        raise LuaError("invalid key to 'next'")
    if pos + 1 < len(keys):
        return (_denormkey(keys[pos + 1]), table.hash[keys[pos + 1]])
    return None

def lua_pairs(table):
    handler = _metamethod(table, "__pairs")
    if handler is not None:
        return lua_adjust(handler(table), 3)
    if not isinstance(table, LuaTable):
        raise _err("bad argument #1 to 'for iterator' (table expected, got %s)"
                       % type_(table))

    def gen():
        for index, value in enumerate(list(table.arr), 1):
            if value is not None:
                yield (index, value)
        for key, value in list(table.hash.items()):
            yield (_denormkey(key), value)
    return _LuaIter(gen())

def lua_rawget(table, key):
    return table.rawget(key)

def lua_rawset(table, key, value):
    table.rawset(key, value)
    return table

def lua_rawequal(a, b):
    return a is b or (type(a) is not bool and type(b) is not bool
                      and not isinstance(a, LuaTable) and a == b)

def lua_rawlen(value):
    return value.length() if isinstance(value, LuaTable) else len(value)

def lua_xpcall(func, handler, *args):
    try:
        return (True,) + lua_multi(func(*args))
    except LuaGoto:
        raise
    except Exception as exc:
        return (False,) + lua_multi(handler(_exc_message(exc)))

def lua_pcall(func, *args):
    try:
        return (True,) + lua_multi(func(*args))
    except LuaGoto:
        raise
    except Exception as exc:
        return (False, _exc_message(exc))

_warn_on = [False]

def lua_warn(*args):
    if len(args) == 1 and args[0] in ("@on", "@off"):
        _warn_on[0] = args[0] == "@on"
    elif _warn_on[0]:
        _sys.stderr.write("Lua warning: " + "".join(lua_tostring(a) for a in args) + "\n")

def _collectable(obj):
    return isinstance(obj, (LuaTable, LuaCoroutine)) or (
        callable(obj) and not isinstance(obj, (str, int, float, bool)))

def _collect_weak():
    for table in list(_weak_tables):
        mode = table.meta.hash.get("__mode") if table.meta is not None else None
        if not isinstance(mode, str):
            continue
        weak_keys, weak_values = "k" in mode, "v" in mode
        keys = list(table.hash.keys())
        for index in range(len(keys)):
            key = keys[index]
            keys[index] = None
            value = table.hash.pop(key)
            dead = (weak_keys and _collectable(key) and _sys.getrefcount(key) <= 2) or (
                weak_values and _collectable(value) and _sys.getrefcount(value) <= 2)
            if not dead:
                table.hash[key] = value
            del key, value
        if weak_values:
            dead = []
            for index in range(len(table.arr)):
                value = table.arr[index]
                if _collectable(value) and _sys.getrefcount(value) <= 3:
                    dead.append(index + 1)
                del value
            for position in reversed(dead):
                table.rawset(position, None)

def lua_collectgarbage(option="collect", *args):
    if option in ("collect", "step"):
        _collect_weak()
        _gc.collect()
        return 0
    if option == "count":
        return 22.5
    return 0

def lua_unsupported(name):
    def func(*args):
        raise LuaError("%s is not supported by this translator" % name)
    return func

def _dynamic_chunk(text):
    try:
        import main as _main_module
        return _main_module.dynamic_chunk(text)
    except Exception:
        return None

def lua_load(chunk, chunkname=None, mode=None, env=None):
    if callable(chunk):
        pieces = []
        while True:
            piece = lua_first(chunk())
            if piece is None or piece == "":
                break
            pieces.append(piece)
        chunk = "".join(pieces)
    if not isinstance(chunk, str):
        raise _err("bad argument #1 to 'load' (string expected, got %s)" % type_(chunk))
    entry = globals().get("_CHUNKS", {}).get(chunk) or _dynamic_chunk(chunk)
    if entry is None:
        first = chunk.split("\n")[0][:40]
        return (None, '[string "%s"]:1: syntax error or untranslatable chunk' % first)
    namespace = globals()
    for name in entry["globals"]:
        namespace.setdefault(name, None)
    exec(compile(entry["code"], "<chunk>", "exec"), namespace)
    return namespace.pop("_lua_chunk")
lua_dofile = lua_unsupported("dofile")
lua_require = lua_unsupported("require")

def lua_close(value, exc):
    if value is None or value is False:
        return
    handler = _metamethod(value, "__close")
    if handler is None:
        return
    error = None
    if exc is not None:
        error = exc.value if isinstance(exc, LuaError) else str(exc)
    handler(value, error)

def lua_checkclose(value, name):
    if value is None or value is False:
        return
    if _metamethod(value, "__close") is None:
        raise LuaError("variable '%s' got a non-closable value" % name)

def _tbl_pack(*args):
    table = lua_table(list(args))
    table["n"] = len(args)
    return table

def _tbl_move(a1, f, e, t, a2=None):
    a2 = a1 if a2 is None else a2
    if e >= f:
        values = [a1[i] for i in range(f, e + 1)]
        for offset, value in enumerate(values):
            a2[t + offset] = value
    return a2

_table_lib["pack"] = _tbl_pack
_table_lib["move"] = _tbl_move

def _m_floor2(x):
    if isinstance(x, int):
        return x
    try:
        r = _math.floor(x)
    except (OverflowError, ValueError):
        return x
    return r if _MINI <= r <= _MAXI else float(r)

def _m_ceil2(x):
    if isinstance(x, int):
        return x
    try:
        r = _math.ceil(x)
    except (OverflowError, ValueError):
        return x
    return r if _MINI <= r <= _MAXI else float(r)

def _m_fmod(a, b):
    if isinstance(a, int) and isinstance(b, int):
        if b == 0:
            raise _err("bad argument #2 to 'fmod' (zero)")
        r = abs(a) % abs(b)
        return -r if a < 0 else r
    try:
        return _math.fmod(a, b)
    except ValueError:
        return float("nan")

def _m_abs(x):
    return -x if x < 0 and x != _MINI else x

_math_lib["floor"] = _m_floor2
_math_lib["ceil"] = _m_ceil2
_math_lib["fmod"] = _m_fmod
_math_lib["abs"] = _m_abs
_math_lib["asin"] = _math.asin
_math_lib["acos"] = _math.acos
_math_lib["atan"] = lambda y, x=1.0: _math.atan2(y, x)
_math_lib["deg"] = _math.degrees
_math_lib["rad"] = _math.radians
_math_lib["ult"] = lambda a, b: (a & 0xFFFFFFFFFFFFFFFF) < (b & 0xFFFFFFFFFFFFFFFF)
_math_lib["modf"] = lambda x: (float(int(x)) if abs(x) != float("inf") else x,
                               0.0 if abs(x) == float("inf") else x - int(x))

_L_ESC = "%"
_CAP_UNFINISHED = -1
_CAP_POSITION = -2

def _class_match(c, cl):
    code = ord(c)
    low = cl.lower()
    if low == "a":
        res = c.isascii() and c.isalpha()
    elif low == "c":
        res = code < 32 or code == 127
    elif low == "d":
        res = "0" <= c <= "9"
    elif low == "g":
        res = 33 <= code <= 126
    elif low == "l":
        res = "a" <= c <= "z"
    elif low == "p":
        res = 33 <= code <= 126 and not c.isalnum()
    elif low == "s":
        res = c in " \t\n\r\f\v"
    elif low == "u":
        res = "A" <= c <= "Z"
    elif low == "w":
        res = c.isascii() and c.isalnum()
    elif low == "x":
        res = c in "0123456789abcdefABCDEF"
    else:
        return cl == c
    return (not res) if cl.isupper() else res

class _Match(object):

    def __init__(self, src, pat):
        self.src = src
        self.pat = pat
        self.level = 0
        self.capture = []
        self.depth = 0

    def pc(self, p):
        return self.pat[p] if p < len(self.pat) else ""

    def class_end(self, p):
        pat, n = self.pat, len(self.pat)
        c = pat[p]
        p += 1
        if c == _L_ESC:
            if p >= n:
                raise LuaError("malformed pattern (ends with '%')")
            return p + 1
        if c == "[":
            if self.pc(p) == "^":
                p += 1
            while True:
                if p >= n:
                    raise LuaError("malformed pattern (missing ']')")
                cc = pat[p]
                p += 1
                if cc == _L_ESC and p < n:
                    p += 1
                if self.pc(p) == "]":
                    break
            return p + 1
        return p

    def bracket(self, c, p, ec):
        pat = self.pat
        sig = True
        if self.pc(p + 1) == "^":
            sig = False
            p += 1
        p += 1
        while p < ec:
            if pat[p] == _L_ESC:
                p += 1
                if _class_match(c, pat[p]):
                    return sig
            elif self.pc(p + 1) == "-" and p + 2 < ec:
                p += 2
                if pat[p - 2] <= c <= pat[p]:
                    return sig
            elif pat[p] == c:
                return sig
            p += 1
        return not sig

    def single(self, s, p, ep):
        if s >= len(self.src):
            return False
        c = self.src[s]
        pc = self.pat[p]
        if pc == ".":
            return True
        if pc == _L_ESC:
            return _class_match(c, self.pat[p + 1])
        if pc == "[":
            return self.bracket(c, p, ep - 1)
        return pc == c

    def balance(self, s, p):
        if p + 1 >= len(self.pat):
            raise LuaError("malformed pattern (missing arguments to '%b')")
        if s >= len(self.src) or self.src[s] != self.pat[p]:
            return -1
        b, e = self.pat[p], self.pat[p + 1]
        cont = 1
        s += 1
        while s < len(self.src):
            ch = self.src[s]
            if ch == e:
                cont -= 1
                if cont == 0:
                    return s + 1
            elif ch == b:
                cont += 1
            s += 1
        return -1

    def max_expand(self, s, p, ep):
        i = 0
        while self.single(s + i, p, ep):
            i += 1
        while i >= 0:
            res = self.match(s + i, ep + 1)
            if res != -1:
                return res
            i -= 1
        return -1

    def min_expand(self, s, p, ep):
        while True:
            res = self.match(s, ep + 1)
            if res != -1:
                return res
            if self.single(s, p, ep):
                s += 1
            else:
                return -1

    def start_capture(self, s, p, what):
        self.capture = self.capture[:self.level]
        self.capture.append([s, what])
        self.level += 1
        res = self.match(s, p)
        if res == -1:
            self.level -= 1
        return res

    def end_capture(self, s, p):
        for index in range(self.level - 1, -1, -1):
            if self.capture[index][1] == _CAP_UNFINISHED:
                break
        else:
            raise LuaError("invalid pattern capture")
        self.capture[index][1] = s - self.capture[index][0]
        res = self.match(s, p)
        if res == -1:
            self.capture[index][1] = _CAP_UNFINISHED
        return res

    def match_capture(self, s, digit):
        index = ord(digit) - ord("1")
        if index < 0 or index >= self.level or self.capture[index][1] == _CAP_UNFINISHED:
            raise LuaError("invalid capture index %%%d" % (index + 1))
        start, length = self.capture[index]
        piece = self.src[start:start + length]
        if self.src.startswith(piece, s):
            return s + length
        return -1

    def match(self, s, p):
        self.depth += 1
        if self.depth > 190:
            self.depth -= 1
            raise LuaError("pattern too complex")
        try:
            return self._match(s, p)
        finally:
            self.depth -= 1

    def _match(self, s, p):
        pat, n = self.pat, len(self.pat)
        while True:
            if p >= n:
                return s
            pc = pat[p]
            if pc == "(":
                if self.pc(p + 1) == ")":
                    return self.start_capture(s, p + 2, _CAP_POSITION)
                return self.start_capture(s, p + 1, _CAP_UNFINISHED)
            if pc == ")":
                return self.end_capture(s, p + 1)
            if pc == "$" and p + 1 == n:
                return s if s == len(self.src) else -1
            if pc == _L_ESC:
                nxt = self.pc(p + 1)
                if nxt == "b":
                    s = self.balance(s, p + 2)
                    if s != -1:
                        p += 4
                        continue
                    return -1
                if nxt == "f":
                    p += 2
                    if self.pc(p) != "[":
                        raise LuaError("missing '[' after '%f' in pattern")
                    ep = self.class_end(p)
                    prev = self.src[s - 1] if s > 0 else "\0"
                    cur = self.src[s] if s < len(self.src) else "\0"
                    if (not self.bracket(prev, p, ep - 1)) and self.bracket(cur, p, ep - 1):
                        p = ep
                        continue
                    return -1
                if nxt.isdigit():
                    s = self.match_capture(s, nxt)
                    if s != -1:
                        p += 2
                        continue
                    return -1
            ep = self.class_end(p)
            epc = self.pc(ep)
            if not self.single(s, p, ep):
                if epc in ("*", "?", "-"):
                    p = ep + 1
                    continue
                return -1
            if epc == "?":
                res = self.match(s + 1, ep + 1)
                if res != -1:
                    return res
                p = ep + 1
                continue
            if epc == "+":
                return self.max_expand(s + 1, p, ep)
            if epc == "*":
                return self.max_expand(s, p, ep)
            if epc == "-":
                return self.min_expand(s, p, ep)
            s += 1
            p = ep

    def get_capture(self, index, s, e):
        if index >= self.level:
            if index != 0:
                raise LuaError("invalid capture index %%%d" % (index + 1))
            return self.src[s:e]
        start, length = self.capture[index]
        if length == _CAP_UNFINISHED:
            raise LuaError("unfinished capture")
        if length == _CAP_POSITION:
            return start + 1
        return self.src[start:start + length]

    def captures(self, s, e, whole_if_none=True):
        count = self.level if (self.level != 0 or not whole_if_none) else 1
        return tuple(self.get_capture(i, s, e) for i in range(count))

def _result(values):
    return values[0] if len(values) == 1 else values

def _str_find_aux(find, s, pattern, init=1, plain=False):
    ls = len(s)
    init = 1 if init is None else int(init)
    if init < 0:
        init = max(ls + init + 1, 1)
    elif init == 0:
        init = 1
    if init > ls + 1:
        return None
    if find and (lua_truth(plain) or not any(ch in "^$*+?.([%-" for ch in pattern)):
        index = s.find(pattern, init - 1)
        if index == -1:
            return None
        return (index + 1, index + len(pattern))
    anchor = pattern.startswith("^")
    pat = pattern[1:] if anchor else pattern
    pos = init - 1
    while True:
        ms = _Match(s, pat)
        e = ms.match(pos, 0)
        if e != -1:
            if find:
                return (pos + 1, e) + ms.captures(pos, e, False)
            return _result(ms.captures(pos, e))
        pos += 1
        if anchor or pos > ls:
            return None

def _str_find(s, pattern, init=1, plain=False):
    return _str_find_aux(True, s, pattern, init, plain)

def _str_match(s, pattern, init=1):
    return _str_find_aux(False, s, pattern, init)

def _str_gmatch(s, pattern, init=1):
    state = {"src": max(int(init) - 1, 0) if init and init > 0 else 0, "last": -1}

    def iterator(*_ignored):
        src = state["src"]
        while src <= len(s):
            ms = _Match(s, pattern)
            e = ms.match(src, 0)
            if e != -1 and e != state["last"]:
                state["src"] = state["last"] = e
                return _result(ms.captures(src, e))
            src += 1
        state["src"] = src
        return None
    return iterator

def _str_gsub(s, pattern, repl, max_n=None):
    anchor = pattern.startswith("^")
    pat = pattern[1:] if anchor else pattern
    limit = len(s) + 1 if max_n is None else int(max_n)
    kind = type(repl)
    if not (kind in (str, int, float) or isinstance(repl, LuaTable) or callable(repl)):
        raise _err("bad argument #3 to 'gsub' (string/function/table expected, got %s)"
                       % type_(repl))
    out = []
    src = 0
    count = 0
    last = -1
    while count < limit:
        ms = _Match(s, pat)
        e = ms.match(src, 0)
        if e != -1 and e != last:
            count += 1
            whole = s[src:e]
            if isinstance(repl, LuaTable):
                value = repl[ms.get_capture(0, src, e)]
            elif callable(repl):
                value = lua_first(repl(*ms.captures(src, e)))
            else:
                value = _gsub_string(ms, lua_tostring(repl), src, e)
            if value is None or value is False:
                out.append(whole)
            elif type(value) in (str, int, float):
                out.append(lua_tostring(value))
            else:
                raise LuaError("invalid replacement value (a %s)" % type_(value))
            src = last = e
        elif src < len(s):
            out.append(s[src])
            src += 1
        else:
            break
        if anchor:
            break
    out.append(s[src:])
    return ("".join(out), count)

def _gsub_string(ms, repl, s, e):
    out = []
    i = 0
    while i < len(repl):
        ch = repl[i]
        if ch != _L_ESC:
            out.append(ch)
        else:
            i += 1
            nxt = repl[i] if i < len(repl) else ""
            if nxt == _L_ESC:
                out.append(_L_ESC)
            elif nxt.isdigit():
                if nxt == "0":
                    out.append(ms.src[s:e])
                else:
                    out.append(lua_tostring(ms.get_capture(int(nxt) - 1, s, e)))
            else:
                raise LuaError("invalid use of '%' in replacement string")
        i += 1
    return "".join(out)

_string_lib["find"] = _str_find
_string_lib["match"] = _str_match
_string_lib["gmatch"] = _str_gmatch
_string_lib["gsub"] = _str_gsub
_string_lib["len"] = lambda s: len(s)

class LuaCoroutine(object):

    def __init__(self, func):
        self.func = func
        self.status = "suspended"
        self.thread = None
        self.to_co = _threading.Semaphore(0)
        self.to_main = _threading.Semaphore(0)
        self.values = ()
        self.error = None
        self.done = False

_co_current = [None]
_co_main = LuaCoroutine(None)
_co_main.status = "running"

def _co_run(co):
    co.to_co.acquire()
    try:
        result = co.func(*co.values)
        co.values = () if result is None else lua_multi(result)
    except Exception as exc:
        co.error = exc if isinstance(exc, LuaError) else LuaError(_exc_message(exc))
    co.status = "dead"
    co.done = True
    co.to_main.release()

def _co_create(func):
    if not callable(func):
        raise _err("bad argument #1 to 'create' (function expected)")
    return LuaCoroutine(func)

def _co_resume(co, *args):
    if co.status == "dead":
        return (False, "cannot resume dead coroutine")
    if co.status != "suspended":
        return (False, "cannot resume non-suspended coroutine")
    prev = _co_current[0]
    if prev is not None:
        prev.status = "normal"
    co.status = "running"
    _co_current[0] = co
    co.values = args
    if co.thread is None:
        co.thread = _threading.Thread(target=_co_run, args=(co,))
        co.thread.daemon = True
        co.thread.start()
    co.to_co.release()
    co.to_main.acquire()
    _co_current[0] = prev
    if prev is not None:
        prev.status = "running"
    if co.done and co.error is not None:
        return (False, co.error.value)
    return (True,) + co.values

def _co_yield(*args):
    co = _co_current[0]
    if co is None:
        raise _err("attempt to yield from outside a coroutine")
    co.values = args
    co.status = "suspended"
    co.to_main.release()
    co.to_co.acquire()
    values = co.values
    return values if len(values) != 1 else values[0]

def _co_wrap(func):
    co = _co_create(func)

    def wrapper(*args):
        result = _co_resume(co, *args)
        if result[0] is True:
            values = result[1:]
            return values if len(values) != 1 else values[0]
        raise LuaError(result[1])
    return wrapper

def _co_status(co):
    return co.status

def _co_running():
    co = _co_current[0]
    return (_co_main, True) if co is None else (co, False)

def _co_close(co):
    if co.status in ("suspended", "dead"):
        co.status = "dead"
        if co.done and co.error is not None:
            return (False, co.error.value)
        return True
    raise LuaError("cannot close a %s coroutine" % co.status)

coroutine = _make_lib({
    "create": _co_create, "resume": _co_resume, "yield": _co_yield,
    "wrap": _co_wrap, "status": _co_status, "running": _co_running,
    "isyieldable": lambda *a: _co_current[0] is not None, "close": _co_close,
})

class LuaFile(object):

    def __init__(self, stream, writable, is_std=False):
        self.stream = stream
        self.writable = writable
        self.is_std = is_std
        self.closed = False

    def __getitem__(self, name):
        return _FILE_METHODS.get(name)

def _f_write(self, *args):
    for item in args:
        if type(item) not in (str, int, float):
            raise _err("bad argument to 'write' (string expected, got %s)" % type_(item))
        text = lua_tostring(item)
        if self.stream is _sys.stdout:
            _out(text)
        elif self.stream is _sys.stderr:
            _sys.stderr.write(text)
        else:
            self.stream.write(text.encode("latin-1", "replace"))
    return self

def _f_read_one(self, fmt):
    stream = self.stream
    if isinstance(fmt, (int, float)):
        data = stream.read(int(fmt)).decode("latin-1")
        return data if data or int(fmt) == 0 else None
    fmt = str(fmt).lstrip("*")
    if fmt.startswith("a"):
        return stream.read().decode("latin-1")
    if fmt.startswith("n"):
        line = stream.readline().decode("latin-1")
        return lua_tonumber(line.strip()) if line else None
    line = stream.readline().decode("latin-1")
    if not line:
        return None
    if fmt.startswith("L"):
        return line
    return line[:-1] if line.endswith("\n") else line

def _f_read(self, *formats):
    if not formats:
        formats = ("l",)
    return tuple(_f_read_one(self, fmt) for fmt in formats) if len(formats) > 1 \
        else _f_read_one(self, formats[0])

def _f_lines(self, *formats):
    def iterator(*_ignored):
        return _f_read(self, *formats)
    return iterator

def _f_close(self):
    if not self.is_std:
        self.stream.close()
    self.closed = True
    return True

_FILE_METHODS = {
    "write": _f_write, "read": _f_read, "lines": _f_lines, "close": _f_close,
    "flush": lambda self: self, "setvbuf": lambda self, *a: True,
}

_stdin_file = LuaFile(_sys.stdin.buffer, False, True)
_stdout_file = LuaFile(_sys.stdout, True, True)
_stderr_file = LuaFile(_sys.stderr, True, True)

def _io_write(*args):
    return _f_write(_stdout_file, *args)

def _io_read(*formats):
    return _f_read(_stdin_file, *formats)

def _io_lines(path=None, *formats):
    if path is None:
        return _f_lines(_stdin_file, *formats)
    try:
        handle = LuaFile(open(path, "rb"), False)
    except OSError as exc:
        raise LuaError("%s: %s" % (path, exc.strerror))
    return _f_lines(handle, *formats)

def _io_open(path, mode="r"):
    try:
        stream = open(path, mode.replace("b", "") + "b")
    except OSError as exc:
        return (None, "%s: %s" % (path, exc.strerror), exc.errno)
    return LuaFile(stream, any(m in mode for m in "wa+"))


_io_lib = _make_lib({
    "write": _io_write, "read": _io_read, "lines": _io_lines, "open": _io_open,
    "stdin": _stdin_file, "stdout": _stdout_file, "stderr": _stderr_file,
    "type": lambda f: ("closed file" if f.closed else "file") if isinstance(f, LuaFile) else None,
})
io = _io_lib

def _os_time(spec=None):
    if spec is None:
        return int(_time.time())
    parts = (int(spec["year"]), int(spec["month"]), int(spec["day"]),
             int(spec["hour"] if spec["hour"] is not None else 12),
             int(spec["min"] or 0), int(spec["sec"] or 0), 0, 0, -1)
    return int(_time.mktime(parts))

def _os_date(fmt="%c", when=None):
    when = _time.time() if when is None else when
    utc = fmt.startswith("!")
    fmt = fmt.lstrip("!")
    moment = _time.gmtime(when) if utc else _time.localtime(when)
    if fmt.startswith("*t"):
        return lua_table([], [
            ("year", moment.tm_year), ("month", moment.tm_mon), ("day", moment.tm_mday),
            ("hour", moment.tm_hour), ("min", moment.tm_min), ("sec", moment.tm_sec),
            ("wday", (moment.tm_wday + 1) % 7 + 1), ("yday", moment.tm_yday),
            ("isdst", bool(moment.tm_isdst))])
    return _time.strftime(fmt, moment)

_os_lib = _make_lib({
    "time": _os_time, "clock": lambda: _time.process_time(), "date": _os_date,
    "getenv": lambda name: _pyos.environ.get(name),
    "difftime": lambda a, b=0: float(a - b),
    "exit": lambda code=None, *a: _sys.exit(0 if code in (None, True) else (1 if code is False else int(code))),
    "remove": lambda p: (True if _pyos.remove(p) is None else None),
    "tmpname": lambda: "/tmp/lua_tmp_%d" % _random.randint(0, 10 ** 9),
})
os = _os_lib

def _u_char(*codes):
    return "".join(chr(int(c)).encode("utf-8", "surrogatepass").decode("latin-1")
                   for c in codes)

def _u_at(s, pos):
    lead = ord(s[pos])
    if lead < 0x80:
        return lead, pos + 1
    if 0xC2 <= lead < 0xE0:
        extra, code = 1, lead & 0x1F
    elif 0xE0 <= lead < 0xF0:
        extra, code = 2, lead & 0x0F
    elif 0xF0 <= lead < 0xF5:
        extra, code = 3, lead & 0x07
    else:
        return None
    if pos + extra >= len(s) + 0 and pos + extra > len(s) - 1:
        return None
    for k in range(1, extra + 1):
        cont = ord(s[pos + k])
        if cont & 0xC0 != 0x80:
            return None
        code = (code << 6) | (cont & 0x3F)
    return code, pos + extra + 1

def _u_range(s, i, j):
    n = len(s)
    i = int(i)
    j = int(j)
    i = i if i >= 0 else n + i + 1
    j = j if j >= 0 else n + j + 1
    return i - 1, j - 1

def _u_len(s, i=1, j=-1):
    pos, last = _u_range(s, i, j)
    count = 0
    while pos <= last:
        decoded = _u_at(s, pos)
        if decoded is None:
            return (None, pos + 1)
        pos = decoded[1]
        count += 1
    return count

def _u_codepoint(s, i=1, j=None):
    pos, last = _u_range(s, i, i if j is None else j)
    points = []
    while pos <= last:
        decoded = _u_at(s, pos)
        if decoded is None:
            raise _err("invalid UTF-8 code")
        points.append(decoded[0])
        pos = decoded[1]
    return tuple(points) if len(points) != 1 else points[0]

def _u_codes(s):
    items = []
    pos = 0
    while pos < len(s):
        decoded = _u_at(s, pos)
        if decoded is None:
            raise _err("invalid UTF-8 code")
        items.append((pos + 1, decoded[0]))
        pos = decoded[1]
    return _LuaIter(iter(items))

utf8 = _make_lib({
    "char": _u_char, "len": _u_len, "codepoint": _u_codepoint, "codes": _u_codes,
    "charpattern": "[\x00-\x7F\xC2-\xFD][\x80-\xBF]*",
})

_G_ALIASES = {
    "print": "lua_print", "tostring": "lua_tostring", "tonumber": "lua_tonumber",
    "pairs": "lua_pairs", "ipairs": "lua_ipairs", "select": "lua_select",
    "error": "lua_error", "assert": "lua_assert", "pcall": "lua_pcall",
    "xpcall": "lua_xpcall", "setmetatable": "lua_setmetatable",
    "getmetatable": "lua_getmetatable", "next": "lua_next", "rawget": "lua_rawget",
    "rawset": "lua_rawset", "rawequal": "lua_rawequal", "rawlen": "lua_rawlen",
    "warn": "lua_warn", "collectgarbage": "lua_collectgarbage", "load": "lua_load",
    "dofile": "lua_dofile", "require": "lua_require", "type": "type_",
}

def _g_pyname(key):
    if key in _G_ALIASES:
        return _G_ALIASES[key]
    if _keyword.iskeyword(key) or hasattr(_builtins, key) or key in ("self", "varargs"):
        return key + "_"
    return key

class _GlobalsTable(LuaTable):

    __slots__ = ()

    def __getitem__(self, key):
        if isinstance(key, str):
            return globals().get(_g_pyname(key))
        return LuaTable.__getitem__(self, key)

    def rawget(self, key):
        return self[key]

    def __setitem__(self, key, value):
        if isinstance(key, str):
            globals()[_g_pyname(key)] = value
        else:
            LuaTable.__setitem__(self, key, value)

_G = _GlobalsTable()
_VERSION = "Lua 5.5"

arg = lua_table([], [(0, "input")])
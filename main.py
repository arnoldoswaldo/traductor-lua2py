import os
import re
import sys

from antlr4 import InputStream, CommonTokenStream

from LuaLexer import LuaLexer
from LuaParser import LuaParser
from traductor import LuaToPython, translate_chunk_text

def translate(source, debug=None, chunks=None):
    parser = LuaParser(CommonTokenStream(LuaLexer(InputStream(source))))
    visitor = LuaToPython(chunks)
    code = visitor.visit(parser.start_())
    if debug is not None:
        debug.update(visitor.debug)
    return code

def dynamic_chunk(text):
    return translate_chunk_text(text, {}, 0)

def load_runtime():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lua_runtime.py")
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read() + "\n\n"
    except OSError:
        return "from lua_runtime import *\n\n"

def build_program(code, chunk="input", debug=None, chunks=None):
    runtime = load_runtime()
    start = runtime.count("\n") + 3
    linemap = {}
    for index, line in enumerate(code.split("\n")):
        match = re.search(r"  #@(\d+)$", line)
        if match:
            linemap[start + index + 1] = int(match.group(1))
    header = ("_CHUNK = %r; _DEBUG = %r; _CHUNKS = %s\n_LINEMAP = %r\n"
              "_USER_START = %d; _LINEKEYS = sorted(_LINEMAP)\n") % (
                  chunk, debug or {}, ascii(chunks or {}), linemap, start)
    return runtime + header + code

def main():
    chunk = sys.argv[1] if len(sys.argv) > 1 else "input"
    source = sys.stdin.buffer.read().decode("latin-1")
    try:
        debug, chunks = {}, {}
        code = translate(source, debug, chunks)
        sys.stdout.write(build_program(code, chunk, debug, chunks))
    except NotImplementedError as exc:
        sys.stderr.write("No soportado todavia: %s\n" % exc)
        sys.exit(1)

if __name__ == "__main__":
    main()
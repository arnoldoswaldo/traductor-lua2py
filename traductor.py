import builtins
import keyword
import re

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener
from antlr4.tree.Tree import TerminalNode

from LuaLexer import LuaLexer
from LuaParser import LuaParser
from LuaParserVisitor import LuaParserVisitor

INDENT = "    "

LITERALS = {"nil": "None", "false": "False", "true": "True",
            "...": "lua_first(varargs)"}

ARITH = {
    "+": "lua_add", "-": "lua_sub", "*": "lua_mul", "/": "lua_div",
    "%": "lua_mod", "//": "lua_idiv", "^": "lua_pow", "&": "lua_band",
    "|": "lua_bor", "~": "lua_bxor", "<<": "lua_shl", ">>": "lua_shr",
    "..": "lua_concat",
}
COMPARISONS = {"==", "~=", "<", ">", "<=", ">="}
LOOPS = ("while", "for", "repeat")

GLOBAL_ALIASES = {
    "print": "lua_print", "tostring": "lua_tostring", "tonumber": "lua_tonumber",
    "pairs": "lua_pairs", "ipairs": "lua_ipairs", "select": "lua_select",
    "error": "lua_error", "assert": "lua_assert", "pcall": "lua_pcall",
    "setmetatable": "lua_setmetatable", "getmetatable": "lua_getmetatable",
    "xpcall": "lua_xpcall", "next": "lua_next", "rawget": "lua_rawget",
    "rawset": "lua_rawset", "rawequal": "lua_rawequal", "rawlen": "lua_rawlen",
    "warn": "lua_warn", "collectgarbage": "lua_collectgarbage",
    "load": "lua_load", "dofile": "lua_dofile", "require": "lua_require",
}

class _ErrorCounter(ErrorListener):
    def __init__(self):
        super().__init__()
        self.count = 0

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        self.count += 1

def translate_chunk_text(text, chunks=None, depth=0):
    counter = _ErrorCounter()
    lexer = LuaLexer(InputStream(text))
    lexer.removeErrorListeners()
    lexer.addErrorListener(counter)
    parser = LuaParser(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    parser.addErrorListener(counter)
    try:
        tree = parser.start_()
        if counter.count:
            return None
        return LuaToPython(chunks, depth).translate_chunk(tree)
    except Exception:
        return None

class _Scope(object):
    def __init__(self):
        self.locals = set()
        self.nonlocals = set()
        self.globals = set()
        self.loops = []
        self.loop_blocks = []

class LuaToPython(LuaParserVisitor):
    def __init__(self, chunks=None, depth=0):
        super().__init__()
        self.chunks = {} if chunks is None else chunks
        self.depth = depth
        self.envs = [{}]
        self.rename_count = {}
        self.hold_env = None
        self.block_locals = {}
        self.level = 0
        self.hoisted = []
        self.scopes = [_Scope()]
        self.counter = 0
        self.globals_seen = set()
        self.debug = {}
        self.flow = []
        self.pure_labels = {}

    def pad(self):
        return INDENT * self.level

    @staticmethod
    def _as_list(value):
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    @staticmethod
    def _name(name):
        if name == "_ENV":
            return "_G"
        if name in GLOBAL_ALIASES:
            return GLOBAL_ALIASES[name]
        if keyword.iskeyword(name) or hasattr(builtins, name) or name in (
                "self", "varargs"):
            return name + "_"
        return name

    def _new_name(self):
        self.counter += 1
        return "_lf%d" % self.counter

    def emit_block(self, block_ctx):
        self.level += 1
        try:
            return self.visit(block_ctx)
        finally:
            self.level -= 1

    def _declare_local(self, name):
        scope = self.scopes[-1]
        scope.locals.add(name)
        for loop_names in scope.loops:
            loop_names.add(name)

    def _loop_body(self, block_ctx, loop_vars=(), kind="while"):
        scope = self.scopes[-1]
        pure = set()
        if kind in ("while", "for") and block_ctx.retstat() is None:
            stats = self._as_list(block_ctx.stat())
            index = len(stats)
            while index > 0 and (stats[index - 1].label() is not None
                                 or stats[index - 1].getChild(0).getText() == ";"):
                index -= 1
            for stat in stats[index:]:
                if stat.label() is not None:
                    name = self._label_name(stat)
                    if not any(self._goto_crossings(block_ctx, name)):
                        pure.add(name)
        self.pure_labels[id(block_ctx)] = pure
        scope.loops.append(set(loop_vars))
        scope.loop_blocks.append(block_ctx)
        self.flow.append(("loop", kind, pure))
        try:
            return self.emit_block(block_ctx)
        finally:
            self.flow.pop()
            scope.loops.pop()
            scope.loop_blocks.pop()

    def _note_assign(self, name):
        if len(self.scopes) == 1:
            return
        scope = self.scopes[-1]
        if name in scope.locals or name in scope.nonlocals or name in scope.globals:
            return
        for outer in reversed(self.scopes[1:-1]):
            if name in outer.locals or name in outer.nonlocals:
                scope.nonlocals.add(name)
                return
            if name in outer.globals:
                scope.globals.add(name)
                return
        scope.globals.add(name)

    @staticmethod
    def _is_call(exp_ctx):
        if exp_ctx.getChildCount() != 1:
            return False
        prefix = exp_ctx.getChild(0)
        if not isinstance(prefix, LuaParser.PrefixexpContext):
            return False
        return (prefix.getChildCount() == 1
                and isinstance(prefix.getChild(0), LuaParser.FunctioncallContext))

    @staticmethod
    def _is_vararg(exp_ctx):
        child = exp_ctx.getChild(0)
        return (exp_ctx.getChildCount() == 1 and isinstance(child, TerminalNode)
                and child.getText() == "...")

    def _single(self, exp_ctx):
        code = self.visit(exp_ctx)
        return "lua_first(%s)" % code if self._is_call(exp_ctx) else code

    def _values(self, exps, expand_last=True):
        out = []
        for i, exp_ctx in enumerate(exps):
            last = i == len(exps) - 1
            if self._is_vararg(exp_ctx):
                out.append("*varargs" if (last and expand_last) else self.visit(exp_ctx))
            elif self._is_call(exp_ctx) and last and expand_last:
                out.append("*lua_multi(%s)" % self.visit(exp_ctx))
            else:
                out.append(self._single(exp_ctx))
        return out

    def _exp_list(self, explist_ctx):
        if explist_ctx is None:
            return []
        return self._as_list(explist_ctx.exp())

    def _fit(self, explist_ctx, count):
        exps = self._exp_list(explist_ctx)
        out = []
        for i, exp_ctx in enumerate(exps[:count]):
            last = i == len(exps) - 1
            shortfall = last and len(exps) < count
            if self._is_vararg(exp_ctx) and shortfall:
                out.append("*lua_adjust(varargs, %d)" % (count - i))
            elif self._is_call(exp_ctx) and shortfall:
                out.append("*lua_adjust(%s, %d)" % (self.visit(exp_ctx), count - i))
            else:
                out.append(self._single(exp_ctx))
        if not (out and out[-1].startswith("*")):
            out += ["None"] * (count - len(out))
        if len(out) == 1 and out[0].startswith("*"):
            out[0] = out[0][1:]
        return out

    def _truth(self, ctx):
        count = ctx.getChildCount()
        if count == 1 and isinstance(ctx.getChild(0), TerminalNode):
            text = ctx.getChild(0).getText()
            if text in ("true", "false", "nil"):
                return "True" if text == "true" else "False"
        if count == 2 and ctx.getChild(0).getText() == "not":
            return "(not %s)" % self._truth(ctx.exp(0))
        if count == 3 and isinstance(ctx.getChild(1), TerminalNode):
            op = ctx.getChild(1).getText()
            if op in COMPARISONS:
                return self.visit(ctx)
            if op in ("and", "or"):
                return "(%s %s %s)" % (
                    self._truth(ctx.exp(0)), op, self._truth(ctx.exp(1)))
        return "lua_truth(%s)" % self.visit(ctx)

    def visitStart_(self, ctx):
        body = self.visit(ctx.chunk())
        prelude = "".join("%s = None\n" % n for n in sorted(self.globals_seen))
        return prelude + body

    RUNTIME_NAMES = {"math", "string", "table", "os", "io", "coroutine", "utf8",
                     "_G", "_VERSION", "type_", "arg"}

    def _lookup(self, lua_name):
        for env in reversed(self.envs):
            if lua_name in env:
                return env[lua_name]
        return None

    def _resolve(self, lua_name):
        binding = self._lookup(lua_name)
        return None if binding is None else binding[0]

    def _bind(self, lua_name, kind="local"):
        base = self._name(lua_name)
        depth = len(self.scopes)
        existing = self._lookup(lua_name)
        rename = False
        if existing is not None:
            if existing[1] == depth or kind in ("local", "localfunc"):
                rename = True
        elif kind in ("local", "localfunc") and base in self.globals_seen:
            rename = True
        name = base
        if rename:
            count = self.rename_count.get(base, 1) + 1
            self.rename_count[base] = count
            name = "%s_%d" % (base, count)
        boxed = kind == "local" and any(
            self._closure_assigns(block, lua_name)
            for block in self.scopes[-1].loop_blocks)
        self.envs[-1][lua_name] = (name, depth, boxed)
        self._declare_local(name)
        return name

    def _names_in_closures(self, node, in_func=False, found=None):
        found = set() if found is None else found
        for i in range(node.getChildCount()):
            child = node.getChild(i)
            if isinstance(child, TerminalNode):
                if in_func and child.getSymbol().type == LuaParser.NAME:
                    found.add(child.getText())
                continue
            self._names_in_closures(
                child, in_func or isinstance(child, LuaParser.FuncbodyContext), found)
        return found

    def _release_locals(self, block_ctx):
        names = self.block_locals.pop(id(block_ctx), [])
        if not names or self.flow and self.flow[-1][0] == "disp":
            return ""
        used = {self._name(n) for n in self._names_in_closures(block_ctx)}
        names = [n for n in names if n not in used and not re.match(r".*_\d+$", n)]
        if not names:
            return ""
        return "%s%s = %s\n" % (self.pad(), " = ".join(names), "None")

    def _closure_assigns(self, node, lua_name, in_func=False):
        for i in range(node.getChildCount()):
            child = node.getChild(i)
            if isinstance(child, TerminalNode):
                continue
            inside = in_func or isinstance(child, LuaParser.FuncbodyContext)
            if inside and isinstance(child, LuaParser.StatContext) \
                    and child.varlist() is not None:
                for var in self._as_list(child.varlist().var()):
                    if var.getChildCount() == 1 and var.getText() == lua_name:
                        return True
            if self._closure_assigns(child, lua_name, inside):
                return True
        return False

    def _describe(self, lua_name, py_name, depth):
        if depth is None:
            return ("global '%s'" % lua_name, py_name)
        if depth == len(self.scopes):
            return ("local '%s'" % lua_name, None)
        return ("upvalue '%s'" % lua_name, None)

    def _record(self, kind, line, description):
        if description is not None:
            entry = self.debug.setdefault(line, {"call": [], "index": []})
            if description not in entry[kind]:
                entry[kind].append(description)

    RUNTIME_NAMES = {"math", "string", "table", "os", "io", "coroutine", "utf8",
                     "_G", "_VERSION", "type_", "arg"}

    def _note_use(self, name):
        if name.startswith("lua_") or name in self.RUNTIME_NAMES:
            return
        self.globals_seen.add(name)

    def translate_chunk(self, tree):
        scope = _Scope()
        self.scopes.append(scope)
        self.envs.append({})
        block = tree.chunk().block()
        body = self.emit_block(block)
        if block.retstat() is None:
            body += INDENT + "return ()\n"
        decl = ""
        if scope.globals:
            decl = "%sglobal %s\n" % (INDENT, ", ".join(sorted(scope.globals)))
        return {"code": "def _lua_chunk(*varargs):\n" + decl + body,
                "globals": sorted(self.globals_seen)}

    def visitChunk(self, ctx):
        return self.visit(ctx.block())

    def visitBlock(self, ctx):
        keep = self.hold_env == id(ctx)
        if keep:
            self.hold_env = None
        self.envs.append({})
        try:
            stats = self._as_list(ctx.stat())
            items = stats + ([ctx.retstat()] if ctx.retstat() is not None else [])
            pure = self.pure_labels.get(id(ctx), set())
            dispatch = [self._label_name(it) for it in stats
                        if it.label() is not None and self._label_name(it) not in pure]
            if dispatch:
                code = self._emit_dispatch(items, set(dispatch))
            else:
                code = self._emit_seq(items)
            return code if code else self.pad() + "pass\n"
        finally:
            if not keep:
                self.block_locals[id(ctx)] = sorted(v[0] for v in self.envs[-1].values())
                self.envs.pop()

    @staticmethod
    def _label_name(stat_ctx):
        return stat_ctx.label().getToken(LuaParser.NAME, 0).getText()

    def _goto_crossings(self, node, label, crossed=False, found=None):
        found = [] if found is None else found
        for i in range(node.getChildCount()):
            child = node.getChild(i)
            if isinstance(child, TerminalNode) or isinstance(
                    child, (LuaParser.FuncbodyContext, LuaParser.FunctiondefContext)):
                continue
            if isinstance(child, LuaParser.StatContext):
                first = child.getChild(0).getText()
                if first == "goto" and child.getChild(1).getText() == label:
                    found.append(crossed)
                self._goto_crossings(child, label, crossed or first in LOOPS, found)
            else:
                self._goto_crossings(child, label, crossed, found)
        return found

    def _emit_break(self):
        top = self.flow[-1] if self.flow else None
        if top is not None and top[0] == "disp":
            top[1]["brk"] = True
            return "%s_brk%d = True\n%sbreak\n" % (self.pad(), top[1]["id"], self.pad())
        return self.pad() + "break\n"

    def _emit_continue(self):
        top = self.flow[-1] if self.flow else None
        if top is not None and top[0] == "disp":
            top[1]["cnt"] = True
            return "%s_cnt%d = True\n%sbreak\n" % (self.pad(), top[1]["id"], self.pad())
        return self.pad() + "continue\n"

    def _close_var(self, item):
        if not isinstance(item, LuaParser.StatContext) or item.attnamelist() is None:
            return None
        if item.getChild(0).getText() != "local":
            return None
        names = self._as_list(item.attnamelist().NAME())
        attribs = self._as_list(item.attnamelist().attrib())
        for name, attrib in zip(names, attribs):
            if attrib.getText() == "<close>":
                return self._resolve(name.getText()) or self._name(name.getText())
        return None

    def _emit_seq(self, items):
        out = []
        for index, item in enumerate(items):
            out.append(self.visit(item))
            name = self._close_var(item)
            if name is not None:
                self.counter += 1
                err = "_ce%d" % self.counter
                pad = self.pad()
                self.level += 1
                rest = self._emit_seq(items[index + 1:]) or self.pad() + "pass\n"
                self.level -= 1
                out.append(
                    "%slua_checkclose(%s, %s)\n" % (pad, name, ascii(name))
                    + "%s%s = None\n%stry:\n%s" % (pad, err, pad, rest)
                    + "%sexcept BaseException as %s_x:\n" % (pad, err)
                    + "%s%s%s = %s_x\n%s%sraise\n" % (pad, INDENT, err, err, pad, INDENT)
                    + "%sfinally:\n%s%slua_close(%s, %s)\n" % (pad, pad, INDENT, name, err))
                break
        return "".join(out)

    def _emit_dispatch(self, items, dispatch):
        self.counter += 1
        uid = self.counter
        segments = [(None, [])]
        for item in items:
            if isinstance(item, LuaParser.StatContext) and item.label() is not None:
                name = self._label_name(item)
                if name in dispatch:
                    segments.append((name, []))
                continue
            segments[-1][1].append(item)
        entry = {"id": uid, "brk": False, "cnt": False}
        self.flow.append(("disp", entry))
        pad = self.pad()
        body = ""
        try:
            self.level += 2
            for index, (_name_, seg_items) in enumerate(segments):
                self.level += 1
                code = self._emit_seq(seg_items) or self.pad() + "pass\n"
                self.level -= 1
                body += "%sif _pc%d <= %d:\n%s" % (self.pad(), uid, index, code)
            self.level -= 2
        finally:
            self.flow.pop()
        handlers = ""
        for index, (name, _items) in enumerate(segments):
            if name is not None:
                handlers += "%sif _g%d.label == %s:\n%s_pc%d = %d\n%scontinue\n" % (
                    pad + INDENT * 2, uid, ascii(name), pad + INDENT * 3, uid, index,
                    pad + INDENT * 3)
        out = "%s_pc%d = 0\n" % (pad, uid)
        if entry["brk"]:
            out += "%s_brk%d = False\n" % (pad, uid)
        if entry["cnt"]:
            out += "%s_cnt%d = False\n" % (pad, uid)
        out += "%swhile True:\n%s%stry:\n%s" % (pad, pad, INDENT, body)
        out += "%sexcept LuaGoto as _g%d:\n%s%s%sraise\n" % (
            pad + INDENT, uid, handlers, pad, INDENT * 2)
        out += "%s%sbreak\n" % (pad, INDENT)
        self.level += 1
        if entry["brk"]:
            out += "%sif _brk%d:\n%s" % (pad, uid, self._emit_break())
        if entry["cnt"]:
            out += "%sif _cnt%d:\n%s" % (pad, uid, self._emit_continue())
        self.level -= 1
        return out

    def visitRetstat(self, ctx):
        saved, self.hoisted = self.hoisted, []
        exps = self._exp_list(ctx.explist())
        if not exps:
            line = "return"
        elif len(exps) == 1:
            line = "return " + (
                "varargs" if self._is_vararg(exps[0]) else self.visit(exps[0]))
        else:
            line = "return (%s)" % ", ".join(self._values(exps))
        pre = "".join(self.hoisted)
        self.hoisted = saved
        return pre + self._mark(self.pad() + line + "\n", ctx.start.line)

    @staticmethod
    def _mark(code, line):
        if not code:
            return code
        first, newline, rest = code.partition("\n")
        return "%s  #@%d%s%s" % (first, line, newline, rest)

    def visitStat(self, ctx):
        saved, self.hoisted = self.hoisted, []
        try:
            code = self._mark(self._stat(ctx), ctx.start.line)
            return "".join(self.hoisted) + code
        finally:
            self.hoisted = saved

    def _stat(self, ctx):
        first = ctx.getChild(0).getText()
        second = ctx.getChild(1).getText() if ctx.getChildCount() > 1 else ""
        if first == ";":
            return ""
        if ctx.varlist() is not None:
            return self._assign(ctx)
        if ctx.functioncall() is not None:
            return self.pad() + self.visit(ctx.functioncall()) + "\n"
        if ctx.label() is not None:
            return ""
        if first == "break":
            return self._emit_break()
        if first == "goto":
            name = ctx.getChild(1).getText()
            loop = next((e for e in reversed(self.flow) if e[0] == "loop"), None)
            if loop is not None and name in loop[2]:
                return self._emit_continue()
            return "%sraise LuaGoto(%s)\n" % (self.pad(), ascii(name))
        if first == "do":
            block = self._as_list(ctx.block())[0]
            code = self.visit(block)
            return code + self._release_locals(block)
        if first == "while":
            return self._while(ctx)
        if first == "repeat":
            return self._repeat(ctx)
        if first == "if":
            return self._if(ctx)
        if first == "for":
            if ctx.getChild(2).getText() == "=":
                return self._for_num(ctx)
            return self._for_in(ctx)
        if first == "function":
            return self._function_stat(ctx)
        if first == "local" and second == "function":
            name = self._bind(ctx.getToken(LuaParser.NAME, 0).getText(), "localfunc")
            return self._funcdef(name, ctx.funcbody())
        if first == "local":
            return self._local(ctx)
        raise NotImplementedError("sentencia no soportada: %s" % ctx.getText())

    def _assign(self, ctx):
        var_ctxs = self._as_list(ctx.varlist().var())
        multi = len(var_ctxs) > 1
        pre, targets = "", []
        for var in var_ctxs:
            if var.getChildCount() == 1:
                lua = var.getText()
                binding = self._lookup(lua)
                if binding is None:
                    name = self._name(lua)
                    self._note_use(name)
                    self._note_assign(name)
                elif not binding[2]:
                    self._note_assign(binding[0])
                targets.append(self.visit(var))
            elif multi:
                prefix = self.visit(var.getChild(0))
                if var.getChild(1).getText() == "[":
                    key = self._single(var.getChild(2))
                else:
                    key = ascii(var.getChild(2).getText())
                self.counter += 1
                obj_name, key_name = "_o%d" % self.counter, "_k%d" % self.counter
                pre += "%s%s, %s = %s, %s\n" % (self.pad(), obj_name, key_name, prefix, key)
                targets.append("%s[%s]" % (obj_name, key_name))
            else:
                targets.append(self.visit(var))
        values = self._fit(ctx.explist(), len(targets))
        return pre + "%s%s = %s\n" % (self.pad(), ", ".join(targets), ", ".join(values))

    def _local(self, ctx):
        lua_names = [n.getText() for n in self._as_list(ctx.attnamelist().NAME())]
        values = self._fit(ctx.explist(), len(lua_names))
        names = [self._bind(n, "local") for n in lua_names]
        code = "%s%s = %s\n" % (self.pad(), ", ".join(names), ", ".join(values))
        for lua, name in zip(lua_names, names):
            if self._lookup(lua)[2]:
                code += "%s%s = [%s]\n" % (self.pad(), name, name)
        return code

    def _while(self, ctx):
        cond = self._truth(ctx.exp(0))
        return "%swhile %s:\n%s" % (
            self.pad(), cond, self._loop_body(self._as_list(ctx.block())[0], (), "while"))

    def _repeat(self, ctx):
        block = self._as_list(ctx.block())[0]
        self.hold_env = id(block)
        body = self._loop_body(block, (), "repeat")
        try:
            cond = self._truth(ctx.exp(0))
        finally:
            self.envs.pop()
        inner = self.pad() + INDENT
        return "%swhile True:\n%s%sif %s:\n%sbreak\n" % (
            self.pad(), body, inner, cond, inner + INDENT)

    def _if(self, ctx):
        exps = self._as_list(ctx.exp())
        blocks = self._as_list(ctx.block())
        out = ""
        for i, cond in enumerate(exps):
            kw = "if" if i == 0 else "elif"
            out += "%s%s %s:\n" % (self.pad(), kw, self._truth(cond))
            out += self.emit_block(blocks[i])
        if len(blocks) > len(exps):
            out += "%selse:\n" % self.pad()
            out += self.emit_block(blocks[-1])
        return out

    def _for_num(self, ctx):
        lua_var = ctx.getToken(LuaParser.NAME, 0).getText()
        bounds = [self._single(e) for e in self._as_list(ctx.exp())]
        self.envs.append({})
        try:
            var = self._bind(lua_var, "for")
            body = self._loop_body(self._as_list(ctx.block())[0], [var], "for")
        finally:
            self.envs.pop()
        return "%sfor %s in lua_range(%s):\n%s" % (
            self.pad(), var, ", ".join(bounds), body)

    def _for_in(self, ctx):
        lua_names = [n.getText() for n in self._as_list(ctx.namelist().NAME())]
        iterables = self._values(self._exp_list(ctx.explist()))
        self.envs.append({})
        try:
            names = [self._bind(n, "for") for n in lua_names]
            target = ", ".join(names) + ("," if len(names) == 1 else "")
            body = self._loop_body(self._as_list(ctx.block())[0], names, "for")
        finally:
            self.envs.pop()
        return "%sfor %s in lua_for(%d, %s):\n%s" % (
            self.pad(), target, len(names), ", ".join(iterables), body)

    def _function_stat(self, ctx):
        funcname = ctx.funcname()
        parts = [c.getText() for c in funcname.getChildren()]
        names = [p for p in parts if p not in (".", ":")]
        is_method = ":" in parts
        root = self._resolve(names[0])
        if root is None:
            root = self._name(names[0])
            self._note_use(root)
        if len(names) == 1 and not is_method:
            self._note_assign(root)
            return self._funcdef(root, ctx.funcbody())
        tmp = self._new_name()
        code = self._funcdef(tmp, ctx.funcbody(), method=is_method)
        target = root + "".join('["%s"]' % n for n in names[1:])
        return code + "%s%s = %s\n" % (self.pad(), target, tmp)

    def _funcdef(self, name, body_ctx, method=False):
        scope = _Scope()
        self.scopes.append(scope)
        self.envs.append({})
        saved_flow, self.flow = self.flow, []
        try:
            params = self._params(body_ctx.parlist(), method)
            body = self.emit_block(body_ctx.block())
            if body_ctx.block().retstat() is None:
                body += self.pad() + INDENT + "return ()\n"
        finally:
            self.scopes.pop()
            self.envs.pop()
            self.flow = saved_flow
        params += self._loop_captures(name, body, scope)
        inner = self.pad() + INDENT
        decl = ""
        if scope.nonlocals:
            decl += "%snonlocal %s\n" % (inner, ", ".join(sorted(scope.nonlocals)))
        if scope.globals:
            decl += "%sglobal %s\n" % (inner, ", ".join(sorted(scope.globals)))
        return "%sdef %s(%s):\n%s%s" % (
            self.pad(), name, ", ".join(params), decl, body)

    def _loop_captures(self, func_name, body, scope):
        captured = set()
        for loop_names in self.scopes[-1].loops:
            captured |= loop_names
        captured -= scope.locals | scope.nonlocals | scope.globals
        captured.discard(func_name)
        return ["%s=%s" % (n, n) for n in sorted(captured)
                if re.search(r"\b%s\b" % re.escape(n), body)]

    def _params(self, parlist_ctx, method):
        lua_names = ["self"] if method else []
        if parlist_ctx.namelist() is not None:
            lua_names += [n.getText() for n in self._as_list(parlist_ctx.namelist().NAME())]
        params = [self._bind(n, "param") + "=None" for n in lua_names]
        has_varargs = "..." in [c.getText() for c in parlist_ctx.getChildren()]
        params.append("*varargs" if has_varargs else "*_extra")
        return params

    def visitExp(self, ctx):
        count = ctx.getChildCount()
        if count == 1:
            child = ctx.getChild(0)
            if isinstance(child, TerminalNode):
                return LITERALS[child.getText()]
            return self.visit(child)
        if count == 2:
            op = ctx.getChild(0).getText()
            if op == "not":
                return "(not %s)" % self._truth(ctx.exp(0))
            operand = self.visit(ctx.exp(0))
            if op == "#":
                return "lua_len(%s)" % operand
            if op == "-":
                inner = ctx.exp(0)
                if (inner.getChildCount() == 1
                        and isinstance(inner.getChild(0), LuaParser.NumberContext)):
                    return "(-%s)" % operand
                return "lua_unm(%s)" % operand
            return "lua_bnot(%s)" % operand
        op = ctx.getChild(1).getText()
        left = self.visit(ctx.exp(0))
        right = self.visit(ctx.exp(1))
        if op == "and":
            return "(%s if lua_truth(_lt := %s) else _lt)" % (right, left)
        if op == "or":
            return "(_lt if lua_truth(_lt := %s) else %s)" % (left, right)
        if op in ("==", "~="):
            return self._equality(ctx, op, left, right)
        if op in COMPARISONS:
            return "(%s %s %s)" % (left, op, right)
        return "%s(%s, %s)" % (ARITH[op], left, right)

    def _equality(self, ctx, op, left, right):
        lits = []
        for exp_ctx in (ctx.exp(0), ctx.exp(1)):
            child = exp_ctx.getChild(0)
            if exp_ctx.getChildCount() == 1 and isinstance(child, TerminalNode) \
                    and child.getText() in ("nil", "true", "false"):
                lits.append("is")
            elif exp_ctx.getChildCount() == 1 and isinstance(child, LuaParser.StringContext):
                lits.append("==")
            else:
                lits.append(None)
        negate = op == "~="
        other = right if lits[0] else left
        if "is" in lits and re.match(r"^\(?-?[\d.'\"]", other):
            lits = [None, None]
        if "is" in lits:
            return "(%s %s %s)" % (left, "is not" if negate else "is", right)
        if "==" in lits:
            return "(%s %s %s)" % (left, "!=" if negate else "==", right)
        call = "lua_eq(%s, %s)" % (left, right)
        return "(not %s)" % call if negate else call

    def visitNumber(self, ctx):
        text = ctx.getText()
        low = text.lower()
        if low.startswith("0x"):
            if "." in low or "p" in low:
                return self._float_literal(float.fromhex(text))
            value = int(text, 16) & 0xFFFFFFFFFFFFFFFF
            return str(value - (1 << 64) if value >= (1 << 63) else value)
        if text.isdigit():
            value = int(text)
            return str(value) if value < (1 << 63) else self._float_literal(float(text))
        return self._float_literal(float(text))

    @staticmethod
    def _float_literal(value):
        if value in (float("inf"), float("-inf")):
            return 'float("%s")' % ("inf" if value > 0 else "-inf")
        return repr(value)

    ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f",
               "v": "\v", "\\": "\\", '"': '"', "'": "'", "\n": "\n"}

    def _unescape(self, body):
        out = []
        i = 0
        while i < len(body):
            ch = body[i]
            if ch != "\\":
                out.append(ch)
                i += 1
                continue
            i += 1
            ch = body[i]
            if ch in self.ESCAPES:
                out.append(self.ESCAPES[ch])
                i += 1
            elif ch == "\r":
                out.append("\n")
                i += 2 if body[i + 1:i + 2] == "\n" else 1
            elif ch == "x":
                out.append(chr(int(body[i + 1:i + 3], 16)))
                i += 3
            elif ch == "z":
                i += 1
                while i < len(body) and body[i] in " \t\n\r\f\v":
                    i += 1
            elif ch.isdigit():
                j = i
                while j < len(body) and j < i + 3 and body[j].isdigit():
                    j += 1
                out.append(chr(int(body[i:j])))
                i = j
            elif ch == "u":
                j = body.index("}", i)
                code = int(body[i + 2:j], 16)
                out.append(chr(code).encode("utf-8", "surrogatepass").decode("latin-1"))
                i = j + 1
            else:
                out.append(ch)
                i += 1
        return "".join(out)

    def visitString(self, ctx):
        text = ctx.getText()
        if ctx.LONGSTRING() is not None:
            opening = re.match(r"\[=*\[", text).group(0)
            content = text[len(opening):-len(opening)].replace("\r\n", "\n")
            if content.startswith("\n"):
                content = content[1:]
            self._maybe_chunk(content)
            return ascii(content)
        value = self._unescape(text[1:-1])
        self._maybe_chunk(value)
        return ascii(value)

    def _maybe_chunk(self, text):
        if text in self.chunks or self.depth >= 3 or len(text) < 4:
            return
        if not re.search(r"[\s(=]", text):
            return
        chunk = translate_chunk_text(text, self.chunks, self.depth + 1)
        if chunk is not None:
            self.chunks[text] = chunk

    def visitFunctiondef(self, ctx):
        name = self._new_name()
        self.hoisted.append(self._funcdef(name, ctx.funcbody()))
        return name

    def visitTableconstructor(self, ctx):
        fieldlist = ctx.fieldlist()
        fields = self._as_list(fieldlist.field()) if fieldlist is not None else []
        positional, keyed = [], []
        for index, field in enumerate(fields):
            first = field.getChild(0).getText()
            exps = self._as_list(field.exp())
            if first == "[":
                keyed.append("(%s, %s)" % (self._single(exps[0]), self._single(exps[1])))
            elif field.getChildCount() == 3 and field.getChild(1).getText() == "=":
                keyed.append('("%s", %s)' % (first, self._single(exps[0])))
            else:
                last = index == len(fields) - 1
                positional.append(self._values(exps, expand_last=last)[0])
        return "lua_table([%s], [%s])" % (", ".join(positional), ", ".join(keyed))

    def visitVar(self, ctx):
        return self._chain(ctx)

    def visitPrefixexp(self, ctx):
        return self._chain(ctx)

    def visitFunctioncall(self, ctx):
        return self._chain(ctx)

    def _args_list(self, args_ctx):
        first = args_ctx.getChild(0)
        if isinstance(first, TerminalNode) and first.getText() == "(":
            return self._values(self._exp_list(args_ctx.explist()))
        return [self.visit(first)]

    def _chain(self, ctx):
        children = [ctx.getChild(i) for i in range(ctx.getChildCount())]
        out = ""
        desc = None
        i = 0
        while i < len(children):
            node = children[i]
            text = node.getText()
            if isinstance(node, TerminalNode):
                line = node.getSymbol().line
                if text == "(":
                    out += "(" + self._single(children[i + 1]) + ")"
                    desc = None
                    i += 3
                elif text == "[":
                    self._record("index", line, desc)
                    out += "[" + self._single(children[i + 1]) + "]"
                    desc = None
                    i += 3
                elif text == ".":
                    self._record("index", line, desc)
                    out += '["%s"]' % children[i + 1].getText()
                    desc = ("field '%s'" % children[i + 1].getText(), None)
                    i += 2
                elif text == ":":
                    self._record("index", line, desc)
                    self._record("call", line, ("method '%s'" % children[i + 1].getText(), None))
                    args = self._args_list(children[i + 2])
                    out = 'lua_callm(%s, "%s"%s)' % (
                        out, children[i + 1].getText(),
                        "".join(", " + a for a in args))
                    desc = None
                    i += 3
                else:
                    binding = self._lookup(text)
                    boxed = False
                    if binding is None:
                        name, depth = self._name(text), None
                        self._note_use(name)
                    else:
                        name, depth, boxed = binding
                    out += name + ("[0]" if boxed else "")
                    desc = self._describe(text, name, depth)
                    i += 1
                continue
            if isinstance(node, LuaParser.ArgsContext):
                self._record("call", node.start.line, desc)
                out += "(" + ", ".join(self._args_list(node)) + ")"
                desc = None
            else:
                out += self.visit(node)
                desc = None
            i += 1
        return out
-- corrutinas
local co = coroutine.create(function(a, b)
  print("inicio", a, b)
  local c = coroutine.yield(a + b)
  print("recibido", c)
  local d, e = coroutine.yield(c * 2)
  print("recibido", d, e)
  return "fin", 99
end)
print(coroutine.status(co))
print(coroutine.resume(co, 1, 2))
print(coroutine.status(co))
print(coroutine.resume(co, 10))
print(coroutine.resume(co, "x", "y"))
print(coroutine.status(co), coroutine.resume(co))
local gen = coroutine.wrap(function() for i = 1, 3 do coroutine.yield(i) end end)
print(gen(), gen(), gen())
local bad = coroutine.create(function() error("boom") end)
print(coroutine.resume(bad))
print(coroutine.isyieldable(), select(2, coroutine.running()))
-- close
local function res(name)
  return setmetatable({}, {__close = function(_, e) print("cerrando", name, e) end})
end
do
  local a <close> = res("A")
  local b <close> = res("B")
  print("dentro")
end
print(pcall(function() local x <close> = res("X"); error("fallo", 0) end))
local k <const> = 5
print(k)
-- patrones
print(string.find("hello world", "o w"), string.find("hello", "l+"), string.find("a.b", ".", 1, true))
print(string.match("key=val", "(%w+)=(%w+)"), string.match("2024-01-05", "(%d+)-(%d+)-(%d+)"))
print(string.gsub("hello world", "o", "0"), string.gsub("abc", "%w", "%0%0"), string.gsub("abc", "", "-"))
for w in string.gmatch("one two  three", "%a+") do io.write("[", w, "]") end
print()
print(string.gsub("hello", "l", {l = "L"}), string.gsub("x y", "%w", function(c) return c:upper() end))
print(("  trim  "):match("^%s*(.-)%s*$") .. "|", ("f(a,b)"):match("%((.-)%)"), ("THE (quick) fox"):find("%((%a+)%)"))
print(string.format("%q", 'a "q"\n'), ("%d items"):format(3), #string.rep("ab", 3))
print(("x"):byte(), string.char(72, 105), ("abc"):sub(-2), ("abc"):upper():lower())
-- utf8
print(utf8.char(72, 228, 8364), utf8.len("häé"), #utf8.char(8364), utf8.codepoint("€", 1))
for p, c in utf8.codes("aé") do io.write(p, ":", c, " ") end
print()
-- errores con posicion
print(pcall(error, "msg"))
print(pcall(function() error("con linea") end))
print(pcall(function() error("nivel 2", 2) end))
print(pcall(function() error({code = 1}) end))
print(pcall(function() local t = nil; return t.x end))
print(pcall(function() return #5 end))
print(pcall(function() return nil .. "x" end))
print(pcall(function() return 1 < "2" end))
print(pcall(function() undefined_fn() end))
print(select(2, pcall(error)))
print(xpcall(function() error("E", 0) end, function(m) return "manejado: " .. m end))
local ok, err = pcall(function() assert(false, "assert msg") end)
print(ok, err, pcall(assert, false), pcall(assert, 1 == 1, "no"))
print(tostring(1e100), 2^31, 10 // 0.0, 255 // 1 | 0, string.format("%5.1f|%g|%i", 2.25, 1e20, 7))
print(next({}), next({10}), type(next), #arg == 0 or true)
print(table.concat({1, 2, 3}, "-"), table.unpack({1, 2, 3}, 2), select(-1, "a", "b", "c"))
print(os.time() > 0, type(os.clock()), os.date("%Y") ~= nil, _VERSION ~= nil, _G.print == print)

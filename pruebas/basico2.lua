-- tablas y arreglos
local t = {10, 20, 30}
t[#t + 1] = 40
table.insert(t, 50)
table.insert(t, 1, 5)
print(#t, t[1], t[#t])
print(table.remove(t), table.remove(t, 1), #t)
print(table.concat(t, ","))
local p = {x = 1, y = 2, ["z w"] = 3}
print(p.x, p.y, p["z w"], p.nada)
p.x = nil
print(p.x)
for i, v in ipairs({"a", "b", "c"}) do io.write(i, "=", v, " ") end
print()
local keys = {}
for k, v in pairs({alpha = 1, beta = 2, gamma = 3}) do keys[#keys + 1] = k end
table.sort(keys)
print(table.concat(keys, " "))
-- closures
local function counter()
  local c = 0
  return function() c = c + 1; return c end
end
local c1, c2 = counter(), counter()
print(c1(), c1(), c1(), c2())
total = 0
local function addg(n) total = total + n end
addg(5); addg(7)
print(total)
-- multiples valores y varargs
local function mm(a, b) return a + b, a * b, a - b end
local s, m = mm(3, 4)
print(s, m, (mm(1, 2)))
print(mm(2, 5))
local function va(...)
  local n = select("#", ...)
  local arr = {...}
  return n, #arr, ...
end
print(va(1, 2, 3))
-- metodos y metatablas
local Animal = {}
Animal.__index = Animal
function Animal.new(name, sound)
  local self = setmetatable({}, Animal)
  self.name = name
  self.sound = sound
  return self
end
function Animal:speak() return self.name .. " dice " .. self.sound end
local Dog = setmetatable({}, {__index = Animal})
Dog.__index = Dog
function Dog.new(name)
  local self = Animal.new(name, "guau")
  return setmetatable(self, Dog)
end
function Dog:fetch() return self.name .. " trae la pelota" end
local d = Dog.new("Rex")
print(d:speak())
print(d:fetch())
-- strings
print(("hola"):upper(), string.rep("ab", 3, "-"), ("hello"):sub(2, 4), #"abc")
print(string.format("%5.2f|%d|%s|%x|%-4d|", 3.14159, 42, "txt", 255, 7))
local str = "mundo"
print(str:len(), str:sub(-3), str:reverse())
-- and / or como valor
local z = nil
print(z or "defecto", 0 and "cero verdadero", nil and 1, false or nil)
-- pcall / error con tabla
local ok, e = pcall(function() error({code = 7}) end)
print(ok, type(e), e.code)
local ok2, r2 = pcall(function(a) return a * 2 end, 21)
print(ok2, r2)
-- math y tipos
print(math.floor(3.7), math.ceil(3.2), math.max(4, 9, 2), math.huge, -math.huge)
print(type(nil), type(1), type("s"), type({}), type(print), tostring(12), tonumber("0x10"), tonumber("abc"))
print(10 / 2, 7 // 2, 2 ^ 10, 7 % 3, 1e3)
-- funcion anonima como argumento
table.sort(t, function(a, b) return a > b end)
print(table.concat(t, ","))
local fs = {}
for i = 1, 3 do fs[i] = function() return i * 10 end end
print(fs[1](), fs[2](), #fs)
-- while con break
local n = 0
while true do n = n + 1; if n >= 5 then break end end
print(n)

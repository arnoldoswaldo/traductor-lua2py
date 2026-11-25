-- iterador personalizado
local function range(n)
  local i = 0
  return function() i = i + 1; if i <= n then return i end end
end
for v in range(4) do io.write(v, " ") end
print()
-- closure en dos niveles que modifica una variable externa
local function outer()
  local total = 0
  local function add(n)
    local function inner() total = total + n end
    inner()
  end
  add(3); add(4)
  return total
end
print(outer())
-- intercambio y tablas anidadas
local a, b = 1, 2
a, b = b, a
print(a, b)
local m = {{1, 2}, {3, 4}}
m[2][1] = 9
print(m[1][2], m[2][1], #m, #m[1])
-- repeat con local en la condicion
local k = 0
repeat local done = k >= 3; k = k + 1 until done
print(k)
-- recursion y rendimiento
local function fib(n) if n < 2 then return n end return fib(n - 1) + fib(n - 2) end
print(fib(24))
-- cadenas
local parts = {}
for i = 1, 5 do parts[#parts + 1] = i * i end
print(table.concat(parts, "+"), #parts)
print(10 == 10.0, "10" == 10, 3 < 4 and "si" or "no")
print(#"", ("x"):rep(0) == "")
local t = {n = 0}
function t:inc() self.n = self.n + 1; return self end
t:inc():inc()
print(t.n)
print(select(2, "a", "b", "c"))
print(tostring(nil), tostring(true), 1 .. 2, 2^0.5 > 1.41)
print(string.format("%3d|%-3d|%03d|%.3s|%5s|%%", 5, 5, 5, "abcdef", "ab"))
goto_skip = 1
print(math.floor(-0.5), 7 // 2.0, -7 // 2, -7 % 3, 5.5 % 2)

local x = 1
if x < 2 then print(x) end
local function f(a, b)
  return a .. b
end
print(f("x", "y"))
-- comentario
local n = 0
while n < 3 do n = n + 1 end
print(n, 7 / 2, 2 ^ 3, 10 // 3, 10 % 3)
for i = 1, 3 do print(i) end
for i = 10, 1, -4 do print(i) end
repeat n = n - 1 until n == 0
print(n, #"hola", not nil, 0 and "cero verdadero")
local a, b = 1
print(a, b, nil, true)
function fact(k)
  if k <= 1 then return 1 else return k * fact(k - 1) end
end
print(fact(5))

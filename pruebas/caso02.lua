print("--- 3.1 Lexical Conventions ---")
local str_escapes = "Linea1\n\tTab\x41\066\u{2603}\z
    ContinuacionSinEspacios"
local long_str = [==[
Texto
Multilinea
Ignora secuencias \n y usa literal]==]
local num_int = 345
local num_hex = 0xBEBADA
local num_float = 314.16e-2
local num_hex_float = 0X1.921FB54442D18P+1
print(str_escapes)
print(long_str)
print(num_int, num_hex, num_float, num_hex_float)
print(0xffffffffffffffff, 9223372036854775807, 9223372036854775808, 1e2, .5, 3.)
for i = 1, 3 do
  for j = 1, 3 do
    if j == 2 then goto continue end
    io.write(i, ":", j, " ")
    ::continue::
  end
end
print()
do
  local k = 0
  ::top::
  k = k + 1
  if k < 3 then goto top end
  print("k", k)
end
for i = 1, 3 do
  for j = 1, 3 do
    if i * j == 4 then goto done end
    io.write(i * j, " ")
  end
end
::done::
print("fin")
local n = 0
while n < 5 do
  n = n + 1
  if n % 2 == 0 then goto skip end
  io.write(n, " ")
  ::skip::
end
print()
local i = 1
repeat
  if i == 2 then goto cont end
  io.write(i, " ")
  ::cont::
  i = i + 1
until i > 4
print()

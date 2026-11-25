-- goto en patrones adicionales
for i = 1, 3 do
  local j = 0
  ::again::
  j = j + 1
  if j < 3 then goto again end
  io.write(i, ":", j, " ")
end
print()
local function find(t, x)
  for i, v in ipairs(t) do
    if v == x then goto found end
  end
  do return "no" end
  ::found::
  return "si"
end
print(find({1, 2, 3}, 2), find({1, 2, 3}, 9))
for i = 1, 4 do
  while true do
    if i % 2 == 0 then goto next_i end
    io.write(i, " ")
    break
  end
  ::next_i::
end
print()
do
  goto skip
  print("no se imprime")
  ::skip::
  print("saltado")
end

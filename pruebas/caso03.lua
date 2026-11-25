print("--- 3.4.1 Arithmetic Operators ---")
local int_val = 10
local float_val = 3.14
print("Suma:", int_val + 5, int_val + float_val, int_val / 3, int_val // 3, -10 // 3)
print("Mod:", int_val % 3, -10 % 3, 2 ^ 3, -int_val, 5.5 // 2, 7 % -3, -7 % 3.5)
print("--- 3.4.2 Bitwise Operators ---")
local b1 = 0xA
local b2 = 0xC
print(b1 & b2, b1 | b2, b1 ~ b2, ~b1, b1 << 2, b1 >> 1, 1 << 63, 1 << 64, -1 >> 60, 3.0 & 1)
print("10" + 5, "3" * "4", "0x10" + 0, 10 .. 20, "10.5" // 2, 2^63, math.tointeger(3.0))
print(pcall(function() return 1 & 1.5 end))
print(pcall(function() return {} + 1 end))
print(1 < 2, "a" < "b", 1 == 1.0, "1" == 1, not nil, not 0)
print(5 // 0.0, -5 // 0.0, 0/0 ~= 0/0, math.huge, -math.huge)
print(pcall(function() return 5 // 0 end))
print(pcall(function() return 5 % 0 end))

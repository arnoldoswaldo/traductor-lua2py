print("--- 3.4.9 Table Constructors ---")
local f_key = function(x) return x * 2 end
local complex_table = {
    [f_key(10)] = "Clave Dinamica",
    "Posicion 1",
    "Posicion 2";
    x = 100,
    [30] = 23;
    "Posicion 3"
}
print("Constructor Posicion 1:", complex_table[1])
print("Constructor Posicion 2:", complex_table[2])
print("Constructor Posicion 3:", complex_table[3])
print("Constructor Clave string (x):", complex_table.x, complex_table[20], complex_table[30], #complex_table)
local function mr() return 1, 2, 3 end
local t = {mr(), mr()}
print(#t, #{mr(), 10}, #{(mr())})
local o = {[1] = "a", "b"}
print(o[1], select("#", table.unpack({1, nil, 3}, 1, 3)))

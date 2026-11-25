local void
void = setmetatable({}, {
    __index = function(t, k)
        print("  [Descendiendo al vacio: " .. tostring(k) .. "]")
        return void
    end,
    __add = function(a, b)
        return type(b) == "string" and ("Eco final: " .. b) or 0x666
    end,
    __call = function(t, ...)
        local args = table.pack(...)
        return (args.n > 0) and (#args * 0xBAD) or "Silencio"
    end,
    __len = function() return 42 end,
    __eq = function() return true end,
    __lt = function() return true end,
    __le = function() return false end,
    __concat = function(a, b) return "cat" end,
    __unm = function() return "neg" end,
    __tostring = function() return "VOID" end,
    __newindex = function(t, k, v) print("set", k, v) end,
})
print(void.a.b.c)
print(void + "hola", void + 1, 1 + void, void(), void(1, 2), #void)
print(void < void, void <= void, void == setmetatable({}, getmetatable(void)), void .. "x", -void)
void.x = 5
print(tostring(void), rawget(void, "x"), rawlen({1, 2}), rawequal(void, void))
local V = {}
V.__index = V
V.__add = function(a, b) return setmetatable({v = a.v + b.v}, V) end
V.__eq = function(a, b) return a.v == b.v end
local a, b = setmetatable({v = 1}, V), setmetatable({v = 2}, V)
print((a + b).v, a == b, a ~= b, a == setmetatable({v = 1}, V))

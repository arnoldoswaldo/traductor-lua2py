local function frankenstein(...)
    return setmetatable({
        (function(a, b) return (a or 0) << (b and 2 or 0) end)(10, true),
        [ (2^3 + "10.5" // 2) & 0xFF ] = function(x, y)
            return (x == type(y)) and (x .. " es valido") or (#tostring(y) * (x | 0))
        end,
        nested = setmetatable({
            base = { table.unpack(table.pack(...), 1, table.pack(...).n) },
            method = function(self, val)
                local a, b = (function() return val ~ 0x0F, val >> 1 end)()
                return (a > b and a or b) + #(self.base)
            end,
        }, {__index = function(t, k) return k .. "?" end}),
    }, {__call = function(self, ...) return select("#", ...) end})
end
local f = frankenstein("a", "b", "c")
print(f[1], f(1, 2, 3), f.nested:method(5), f.nested.zzz)
print(f[13]("string", "x"), f[13](3, 4))

--- @meta
--- @diagnostic disable: undefined-doc-name, duplicate-doc-field, duplicate-doc-alias

--- @class LuaScriptSignal
--- Signal definition for Lua scripts.
LuaScriptSignal = {}

--- @return bool
function LuaScriptSignal:is_null() end

--- @return Object
function LuaScriptSignal:get_object() end

--- @return number
function LuaScriptSignal:get_object_id() end

--- @return StringName
function LuaScriptSignal:get_name() end

--- @param callable Callable
--- @param flags number? @default `0`
--- @return number
function LuaScriptSignal:connect(callable, flags) end

--- @param callable Callable
function LuaScriptSignal:disconnect(callable) end

--- @param callable Callable
--- @return bool
function LuaScriptSignal:is_connected(callable) end

--- @return Array
function LuaScriptSignal:get_connections() end

--- @return bool
function LuaScriptSignal:has_connections() end

function LuaScriptSignal:emit(...) end

--- Used to define custom signals in Lua scripts.
--- For now there is no way to pass type information for arguments, only their names.
--- ```
--- local MyClass = {}
--- MyClass.some_signal = signal("argument1", "argument2")
--- return MyClass
--- ```
--- @param ... string
--- @return LuaScriptSignal
function signal(...) end

import requests
import pathlib
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

CACHE = pathlib.Path("godot_docs")
CACHE.mkdir(exist_ok=True)

# potentially add translation (.po) support
# https://github.com/godotengine/godot/blob/master/doc/translations
DOC_LANGUAGE = "en"
DOC_DIR = CACHE / f"{DOC_LANGUAGE}"
DOC_DIR.mkdir(exist_ok=True)

# example xml file
# https://raw.githubusercontent.com/godotengine/godot/refs/heads/master/doc/classes/%40GlobalScope.xml
ENGINE_DOCS_BASE = "https://raw.githubusercontent.com/godotengine/godot/refs/heads/master/doc/classes"

def get_class_xml(name: str) -> str:
    path = DOC_DIR / f"{name}.xml"
    url = f"{ENGINE_DOCS_BASE}/{name}.xml"

    if not path.exists():
        print("fetching", url)
        text = requests.get(url).text
        path.write_text(text, encoding="utf-8")

    return path.read_text(encoding="utf-8")


def parse_godot_class_xml(xml_text: str) -> Dict[str, Any]:
    root = ET.fromstring(xml_text)

    if root.tag != "class":
        raise ValueError("Expected root tag <class>")

    class_data: Dict[str, Any] = {
        "name": root.get("name"),
        "inherits": root.get("inherits"),
        "version": root.get("version"),
        "api_type": root.get("api_type"),
        "brief_description": "",
        "description": "",
        "tutorials": [],
        "constants": {},
        "methods": {},
        "members": {},
        "signals": {},
        "theme_items": {},
    }

    for child in root:
        tag = child.tag

        if tag == "brief_description":
            class_data["brief_description"] = (child.text or "").strip()

        elif tag == "description":
            class_data["description"] = (child.text or "").strip()

        elif tag == "tutorials":
            for link in child.findall("link"):
                class_data["tutorials"].append({
                    "title": link.get("title", ""),
                    "href": (link.text or "").strip()
                })

        elif tag == "constants":
            for const in child.findall("constant"):
                name = const.get("name")
                if name:
                    class_data["constants"][name] = {
                        "value": const.get("value"),
                        "enum": const.get("enum"),
                        "description": (const.text or "").strip()
                    }

        elif tag == "methods":
            for method in child.findall("method"):
                name = method.get("name")
                if not name:
                    continue

                qualifiers = method.get("qualifiers")

                # Return type
                return_elem = method.find("return")
                return_type = return_elem.get("type") if return_elem is not None else "void"

                # Arguments
                arguments: List[Dict[str, str]] = []
                for arg in method.findall("param"):
                    arguments.append({
                        "index": int(arg.get("index", 0)),
                        "name": arg.get("name", ""),
                        "type": arg.get("type", ""),
                        # default value if present in newer XML
                        "default": arg.get("default")
                    })
                # Sort by index just in case
                arguments.sort(key=lambda a: a["index"])

                description = ""
                desc_elem = method.find("description")
                if desc_elem is not None:
                    description = (desc_elem.text or "").strip()

                class_data["methods"][name] = {
                    "qualifiers": qualifiers,
                    "return_type": return_type,
                    "arguments": arguments,
                    "description": description,
                }

        elif tag == "members":
            for member in child.findall("member"):
                name = member.get("name")
                if name:
                    class_data["members"][name] = {
                        "type": member.get("type"),
                        "setter": member.get("setter"),
                        "getter": member.get("getter"),
                        "default": member.get("default"),
                        "description": (member.text or "").strip(),
                    }

        elif tag == "signals":
            for signal in child.findall("signal"):
                name = signal.get("name")
                if not name:
                    continue

                arguments: List[Dict[str, str]] = []
                for arg in signal.findall("argument"):
                    arguments.append({
                        "index": int(arg.get("index", 0)),
                        "name": arg.get("name", ""),
                        "type": arg.get("type", ""),
                    })
                arguments.sort(key=lambda a: a["index"])

                description = ""
                desc_elem = signal.find("description")
                if desc_elem is not None:
                    description = (desc_elem.text or "").strip()

                class_data["signals"][name] = {
                    "arguments": arguments,
                    "description": description,
                }

        elif tag == "theme_items":
            for item in child.findall("theme_item"):
                name = item.get("name")
                if name:
                    class_data["theme_items"][name] = {
                        "type": item.get("type"),
                        "description": (item.text or "").strip(),
                    }

    return class_data

def get_class_data(name: str) -> Dict[str, Any]:
    xml_text = get_class_xml(name)
    return parse_godot_class_xml(xml_text)

godot_type_to_lua_mapping = {
    # "int": "integer",
    # "float": "float",
    # "bool": "boolean",
    # "String": "string",
    # "StringName": "string",
    # "NodePath": "string",
    # "Array": "table",
    # "Dictionary": "table",
    # "Variant": "any",
    # "void": "nil",
    # "Object": "table",
}
def godot_type_to_lua(godot_type: str) -> str:
    return godot_type_to_lua_mapping.get(godot_type, godot_type)

godot_param_name_to_lua_mapping = {
    "end": "_end"
}
def godot_param_name_to_lua(godot_name: str) -> str:
    return godot_param_name_to_lua_mapping.get(godot_name, godot_name)

def xml_to_md(xml_text):
    text = xml_text.replace("	", "").strip()
    # text = text.replace("\n", " ")
    text = text.replace("\n", "\n--- ")

    # bold
    text = text.replace("[b]", "**").replace("[/b]", "**")

    # codeblocks
    text = text.replace("[code]", "`").replace("[/code]", "`")
    text = text.replace("[codeblock]", "```gdscript").replace("[/codeblock]", "```")

    return text

def godot_class_to_lua_annotations(class_data: dict) -> str:
    """Convert parsed Godot class XML data into LuaLS annotation comments."""
    lines = []

    class_name = class_data["name"]
    inherits = class_data.get("inherits")

    is_global = class_name == "@GlobalScope"

    def parse_args(tbl):
        args = tbl.get("arguments", [])
        params = []
        for arg in args:
            arg_name = godot_param_name_to_lua(arg.get("name", f"arg{arg.get("index", 0)}"))
            arg_type = arg.get("type", "any")
            # arg_type = arg.get("type", "nil")
            # LLS uses lowercase common types: number, string, boolean, table, etc.
            lua_type = godot_type_to_lua(arg_type)

            params.append(arg_name)
            # lines.append(f"{arg_name}:{lua_type}")
            lines.append(f"---@param {arg_name} {lua_type}")
        return args, ", ".join(params)

    def separate_comment(txt):
        return txt.replace("\n", "\n\n")

    # class / global scope
    if not is_global: 
        lines.append(f"--- @class {class_name}")
        if inherits:
            lines.append(f"--- @field super {inherits}") # or use inheritance if your Lua binding supports it
    # full description
    if class_data["brief_description"]:
        brief_description = class_data["brief_description"]
        lines.append(f"--- {brief_description}")
        lines.append("---")
    if class_data["description"]:
        description = separate_comment(class_data["description"])
        lines.append(f"--- {description}")
    if not is_global: lines.append(f"{class_name} = {{}}")
    lines.append("")

    # constants
    if class_data["constants"]:
        lines.append("\n--- [[ Constants ]]\n")
        for name, const in sorted(class_data["constants"].items()):
            value = const.get("value", "nil")
            desc = const.get("description", "")
            enum = const.get("enum", "")

            if enum: lines.append(f"--- @type {enum}")
            lines.append(f"--- {desc}")
            if is_global: 
                lines.append(f"{name} = {value}")
            else:
                lines.append(f"{class_name}.{name} = {value}")
        lines.append("")

    # members (Properties)
    if class_data["members"]:
        lines.append("\n--- [[ Properties ]]\n")
        for name, member in sorted(class_data["members"].items()):
            # {'type': 'Geometry2D', 'setter': '', 'getter': '', 'default': None, 'description': 'The [Geometry2D] singleton.'}
            typ = godot_type_to_lua(member.get("type", "any"))
            if member["description"]:
                lines.append(f"--- {separate_comment(member["description"])}")
            lines.append(f"--- @type {typ}")
            if is_global: 
                lines.append(f"{name} = nil")
            else:
                lines.append(f"{class_name}.{name} = nil")
        lines.append("")

    # signals
    if class_data["signals"]:
        lines.append("\n--- [[ Signals ]]\n")
        for name, sig in class_data["signals"].items():
            desc = sig.get("description", "")
            arguments = sig.get("arguments")
            parse_args(sig)

            if desc:
                lines.append(f"--- {desc}")
            
            if is_global: 
                lines.append(f"\n{name} = signal()")
            else:
                lines.append(f"\n{class_name}.{name} = signal()")
        lines.append("")

    # methods
    if class_data["methods"]:
        lines.append("\n--- [[ Methods ]]\n")
        for name, method in sorted(class_data["methods"].items()):
            return_type = godot_type_to_lua(method.get("return_type", "void"))
            if name == "clamp":
                print(method)

            # build parameter list
            args, params = parse_args(method)

            # description
            desc = method.get("description", "")

            # qualifiers (e.g. vararg, const)
            qualifiers = method.get("qualifiers")
            if qualifiers:
                desc = f"[{qualifiers}] {desc}".strip()

            # write the annotation block
            if return_type != "nil":
                lines.append(f"---@return {return_type}")

            if desc:
                lines.append(f"--- {desc}")

            # The actual function declaration (for completion + hover)
            if is_global: 
                lines.append(f"function {name}({params}) end")
            else:
                lines.append(f"function {class_name}.{name}({params}) end")
            lines.append("")

    # theme items (rarely needed for Lua)
    if class_data.get("theme_items"):
        lines.append("\n--- [[ Theme Items ]]\n")
        for name, item in class_data["theme_items"].items():
            typ = godot_type_to_lua(item.get("type", "any"))
            desc = item.get("description", "")
            if desc: 
                lines.append(f"--- {desc}")
            lines.append(f"--- @field {name} {typ}")
        
    page = [
        "---@diagnostic disable: missing-return, undefined-doc-name, assign-type-mismatch"
    ]
    for line in lines:
        page.append(xml_to_md(line))

    return "\n".join(page)

def get_godot_class_lua_annotations(cls):
    path = DOC_DIR / f"{cls}.lua"

    text = godot_class_to_lua_annotations(get_class_data(cls))
    path.write_text(text, encoding="utf-8")

    return text

def _class_test():
    _class = "@GlobalScope"
    # _class = "MultiplayerPeer"
    # print(get_godot_class_lua_annotations(_class))
    get_godot_class_lua_annotations(_class)

if __name__ == "__main__":
    _class_test()
    # _globals_test()
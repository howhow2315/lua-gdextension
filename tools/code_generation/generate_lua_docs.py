import re, requests, pathlib
import xml.etree.ElementTree as ET

CACHE = pathlib.Path("godot_docs")
CACHE.mkdir(exist_ok=True)

GODOT_VER = "master"
GODOT_VER = "4.6"

# potentially add translation (.po) support
# https://github.com/godotengine/godot/blob/master/doc/translations
# DOC_LANGUAGE = "en"
DOC_DIR = CACHE / f"{GODOT_VER}"
DOC_DIR.mkdir(exist_ok=True)

# example xml file
# https://raw.githubusercontent.com/godotengine/godot/refs/heads/master/doc/classes/%40GlobalScope.xml
DOCS_BASE = f"https://raw.githubusercontent.com/godotengine/godot/refs/heads/{GODOT_VER}/doc/classes"

# https://docs.godotengine.org/en/stable/classes/class_multiplayerpeer.html
WIKI_VER = "stable"
WIKI_URL_BASE = f"https://docs.godotengine.org/en/{WIKI_VER}"
WIKI_URL_BASE_CLASS = f"{WIKI_URL_BASE}/classes/class_"

# example local wiki reference
# [constant PROPERTY_USAGE_SCRIPT_VARIABLE]
# could we link to our definition instead? i think that might be better
# ---@see PROPERTY_USAGE_SCRIPT_VARIABLE
# https://docs.godotengine.org/en/stable/classes/class_@globalscope.html#class-globalscope-constant-property-usage-script-variable

def get_class_xml(name: str) -> str:
    path = DOC_DIR / f"{name}.xml"
    url = f"{DOCS_BASE}/{name}.xml"

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

                # return type
                return_elem = method.find("return")
                return_type = return_elem.get("type") if return_elem is not None else "void"

                # arguments
                arguments: List[Dict[str, str]] = []
                for arg in method.findall("param"):
                    arguments.append({
                        "index": int(arg.get("index", 0)),
                        "name": arg.get("name", ""),
                        "type": arg.get("type", ""),
                        "default": arg.get("default")
                    })
                # sort by index just in case
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

    return class_data

def get_class_data(name: str) -> Dict[str, Any]:
    xml_text = get_class_xml(name)
    return parse_godot_class_xml(xml_text)

godot_type_to_lua_mapping = {
    # "int": "integer",
    # "float": "float",
    "bool": "boolean",
    None: "nil"
}
def godot_type_to_lua(godot_type: str) -> str:
    return godot_type_to_lua_mapping.get(godot_type, godot_type)

# fix invalid mappings due to syntax differences across languages
godot_param_name_to_lua_mapping = {
    "end": "_end"
}
def godot_param_name_to_lua(godot_name: str) -> str:
    return godot_param_name_to_lua_mapping.get(godot_name, godot_name)

def xml_to_md(text, class_name):
    # references (example: [method Image.rotate_90])
    def repl_ref(m):
        kind = m.group(1)
        name = m.group(2)

        is_global = class_name == "@GlobalScope"
        scope = class_name
        class_part = class_name.lower()

        # anchor formatting differs slightly per type
        anchor = f"class-{class_part}-{kind}-{name.lower()}"

        url = f"{WIKI_URL_BASE_CLASS}{class_part}.html#{anchor}"
        link = f"[{name}]({url})"

        if is_global:
            return f"{link}\n--- @see {name}"
        else:
            return f"{link}\n--- @see {scope}.{name}"
        
    text = re.sub(
        r"\[(constant|member|method|signal|enum|param)\s+([A-Za-z0-9_]+)\]",
        repl_ref,
        text
    )

    # url blocks (example: [url=https://github.com/godotengine/godot/issues]the GitHub Issue Tracker[/url])
    def repl_url(m):
        url = m.group(1)
        text = m.group(2)
        return f"[{text}]({url})"

    text = re.sub(
        r"\[url=(.*?)\](.*?)\[/url\]",
        repl_url,
        text,
        flags=re.DOTALL
    )

    # titled href; [$CLASS] -> [$CLASS]($DOCS_URL/$CLASS)
    def repl(m):
        name = m.group(1)
        return f"[{name}]({WIKI_URL_BASE_CLASS}{name.lower()}.html)"

    text = re.sub(
        r"\[([A-Z][A-Za-z0-9_]*)\](?!\()",
        repl,
        text
    )

    # whitespace
    text = text.replace("	", "").strip()

    # newlines
    # text = text.replace("\n", " ")
    # text = text.replace("\n", "\n--- ")

    # bold
    text = text.replace("[b]", "**").replace("[/b]", "**")

    # italics
    text = text.replace("[i]", "*").replace("[/i]", "*")

    #code
    text = text.replace("[code]", "`").replace("[/code]", "`")
    
    # codeblock
    text = text.replace("[codeblock]", "```gdscript").replace("[/codeblock]", "```")
    text = text.replace("[gdscript]", "```gdscript\n--- # GDScript").replace("[/gdscript]", "```")
    text = text.replace("[csharp]", "\n--- ```csharp\n--- // C#").replace("[/csharp]", "```")

    # codeblocks
    text = text.replace("[codeblocks]", "").replace("[/codeblocks]", "")

    return text

def godot_class_to_lua_annotations(class_data: dict) -> str:
    """Convert parsed Godot class XML data into LuaLS annotation comments."""

    class_name = class_data["name"]
    inherits = class_data.get("inherits")

    is_global = class_name == "@GlobalScope"

    lines = [
        f"---@diagnostic disable: missing-return, undefined-doc-name, assign-type-mismatch{is_global and ", lowercase-global" or ""}",
        ""
    ]

    # helpers
    def parse_args(tbl):
        args = tbl.get("arguments", [])
        params = []
        for arg in args:
            arg_name = godot_param_name_to_lua(arg.get("name", f"arg{arg.get("index", 0)}"))
            arg_type = godot_type_to_lua(arg.get("type", "any"))

            params.append(arg_name)
            lines.append(f"---@param {arg_name} {arg_type}")
        return args, ", ".join(params)

    def clean_comment(txt):
        return txt.replace("\n", "\n--- ")

    def add_section(_title):
        lines.append("")
        lines.append(f"--- [[ {_title} ]]")
        lines.append("")

    def add_description(_desc, _append = ""):
        if _desc:
            lines.append(f"--- {clean_comment(_desc)}")
            if _append:
                lines.append(_append)

    # class / global scope
    if not is_global: 
        lines.append(f"--- @class {class_name}")
        if inherits:
            lines.append(f"--- @field super {inherits}") # TODO potentially use inheritance instead if LLS works better with it

    # full description
    add_description(class_data.get("brief_description", ""), "---")
    add_description(class_data.get("description", ""))

    # tutorials
    if not is_global:
        tutorials = class_data["tutorials"]
        if tutorials:
            for tutorial in tutorials:
                lines.append("---")
                lines.append(f"--- **Tutorial:** [{tutorial["title"]}]({tutorial["href"].replace("$DOCS_URL", WIKI_URL_BASE)})")
        lines.append(f"{class_name} = {{}}")
    lines.append("")

    # constants
    if class_data["constants"]:
        add_section("Constants")
        for name, const in sorted(class_data["constants"].items()):
            value = const.get("value", "nil")
            enum = const.get("enum", "")
            add_description(const.get("description", ""))

            if enum: lines.append(f"--- @type {enum}")
            if is_global: 
                lines.append(f"{name} = {value}")
            else:
                lines.append(f"{class_name}.{name} = {value}")
            lines.append("")

    # members (Properties)
    if class_data["members"]:
        add_section("Properties")
        for name, member in sorted(class_data["members"].items()):
            # {'type': 'Geometry2D', 'setter': '', 'getter': '', 'default': None, 'description': 'The [Geometry2D] singleton.'}
            value = member.get("default", "nil")
            add_description(member.get("description", ""))
            
            if is_global:
                # subclasses (aka global members/singletons)
                if value == None:
                    value = "{}"
            else:
                value = godot_type_to_lua(value)
                
            typ = godot_type_to_lua(member.get("type", "any"))
            
            lines.append(f"--- @type {typ}")
            if is_global: 
                lines.append(f"{name} = {value}")
            else:
                lines.append(f"{class_name}.{name} = {value}")
            lines.append("")

    # signals
    if class_data["signals"]:
        add_section("Signals")
        for name, sig in class_data["signals"].items():
            arguments = sig.get("arguments")
            args, params = parse_args(sig)
            add_description(sig.get("description", ""))

            if is_global: 
                lines.append(f"{name} = signal()")
            else:
                lines.append(f"{class_name}.{name} = signal()")
            lines.append("")

    # methods
    if class_data["methods"]:
        add_section("Methods")
        for name, method in sorted(class_data["methods"].items()):
            return_type = godot_type_to_lua(method.get("return_type", "void"))

            # build parameter list
            args, params = parse_args(method)

            # write the annotation block
            if return_type != "nil": lines.append(f"---@return {return_type}")

            # description
            desc = clean_comment(method.get("description", ""))

            # qualifiers (e.g. vararg, const)
            # i dont think we can apply this to Lua, but the info itself is valuable
            qualifiers = method.get("qualifiers")
            if qualifiers: desc = f"[{qualifiers}] {desc}".strip()

            if desc: lines.append(f"--- {desc}")

            # The actual function declaration (for completion + hover)
            if is_global: 
                lines.append(f"function {name}({params}) end")
            else:
                lines.append(f"function {class_name}.{name}({params}) end")
            lines.append("")

    return xml_to_md("\n".join(lines), class_name)

def get_godot_class_lua_annotations(cls):
    path = DOC_DIR / f"{cls}.lua"

    text = godot_class_to_lua_annotations(get_class_data(cls))
    path.write_text(text, encoding="utf-8")

    return text

def _class_test():
    _class = "@GlobalScope"
    # _class = "MultiplayerPeer"
    get_godot_class_lua_annotations(_class)

if __name__ == "__main__":
    _class_test()
    # _globals_test()
import requests
import re
import pathlib
from pathlib import Path

CACHE = pathlib.Path("godot_docs")
CACHE.mkdir(exist_ok=True)

DOC_LANGUAGE = "en"
DOC_DIR = CACHE / f"{DOC_LANGUAGE}"
DOC_DIR.mkdir(exist_ok=True)

DOC_GODOT_VERSION = "stable"
DOCS_URL_BASE = f"https://docs.godotengine.org/{DOC_LANGUAGE}"

CLASS_URL_BASE = f"{DOCS_URL_BASE}/{DOC_GODOT_VERSION}/classes"
CLASS_SOURCE_URL_BASE = f"{DOCS_URL_BASE}/_sources/classes"

GLOBALS_URL = f"{DOCS_URL_BASE}/classes/class_%40globalscope.html" # `#enum-globalscope-mousebuttonmask`
GLOBALS_SOURCE_URL = f"{DOCS_URL_BASE}/_sources/classes/class_%40globalscope.rst.txt"
GLOBALS_PATH = CACHE / "@globals.rst.txt"


def get_rst(path, url):
    print(path, url)
    if not path.exists():
        page = requests.get(url)
        path.write_text(page.text, encoding="utf-8")
        print(page.text)
    return path.read_text(encoding="utf-8")

def get_class_rst(name):
    name = name.lower()

    class_file = f"class_{name}.rst.txt"
    path = DOC_DIR / class_file
    url = f"{CLASS_URL_BASE}/{class_file}"

    return get_rst(path, url)

def get_globals_rst():
    return get_rst(GLOBALS_PATH, GLOBALS_SOURCE_URL)


def godot_ref_to_md(line: str) -> str:
    """Convert Godot <class_...> and <enum_...> references, and standard URLs to Markdown links."""
    
    def repl(match):
        text, identifier = match.groups()
        
        if "_property_" in identifier: # handle class references with properties
            parts = identifier.split("_property_")
            class_part = parts[0].replace("class_", "").lower()
            property_part = parts[1].replace("_", "-").replace("/", "-")
            url = f"{CLASS_URL_BASE}/class_{class_part}.html#class-{class_part}-property-{property_part}"

        elif "_enum_" in identifier: # handle enum references
            parts = identifier.split("_enum_")
            enum_part = parts[1].replace("_", "-").lower()
            url = f"{CLASS_URL_BASE}/enum_{enum_part}.html"

        elif "_@globalscope_" in identifier: # handle @GlobalScope references
            parts = identifier.split("_@globalscope_")
            global_part = parts[1].lower()
            url = f"{GLOBALS_URL}#{global_part}"

        else: # handle class references without properties
            class_part = identifier.replace("class_", "").lower()
            url = f"{CLASS_URL_BASE}/class_{class_part}.html"
        
        return f"[{text}]({url})"
    
    def url_repl(match):
        # match text followed by a URL in angle brackets and format it into a Markdown link
        text, url = match.group(1), match.group(2)
        return f"[{text}]({url})"

    # convert Godot class references (<class_...>)
    line = re.sub(r'([^\s`]+)<class_([^>]+)>', repl, line)

    # convert Godot enum references (<enum_...>)
    line = re.sub(r'([^\s`]+)<enum_([^>]+)>', repl, line)

    # convert text <URL> into Markdown [text](URL) and remove backticks
    line = re.sub(r'`([^\s`]+) <(https?://[^\s>]+)>`', url_repl, line)
    
    return line


def parse_doc_block(block: str) -> tuple[str, str] | None:
    """Parse a property or method block."""

    lines = block.splitlines()
    if not lines:
        return None

    name = lines[0].rstrip(":").strip()
    doc_lines = []
    in_doc = False

    for line in lines[1:]:
        if not line:
            if in_doc:
                doc_lines.append("")
            continue

        # skip RST directives, anchors, set/get signatures
        if any(line.startswith(p) for p in [".. rst-class::", "- |", ".. _", ".. |"]) or (line.startswith("-") and "**" in line):
            continue        

        in_doc = True
        line = godot_ref_to_md(line)
        line = line.replace("``", "`")
        line = re.sub(r':ref:`([^`]+)`', r'\1', line)
        line = line.rstrip("`").replace("__", "").replace("|", "")
        doc_lines.append(line)

    if doc_lines:
        while doc_lines and doc_lines[-1] in ("", "----"):
            doc_lines.pop()
        return name, "\n".join(doc_lines)

    return None


def parse_section(key: str, splitter_keyword: str, text: str) -> dict[str, str]:
    """Parse all blocks within a given section specified by the splitter keyword."""

    # find the starting index of the section by the keyword
    section_split = re.split(rf"\n{splitter_keyword}\n[-]+\n", text)

    # if no match is found, return empty dict
    if len(section_split) < 2:
        # print(f"error cant find section match for {splitter_keyword} to parse")
        return {}

    # extract the section starting from the second split part
    section_text = section_split[1]

    # look for the stop marker and cut off everything after it
    stop_index = section_text.find(".. rst-class:: classref-descriptions-group")
    if stop_index != -1:
        section_text = section_text[:stop_index]
    
    # split by the class definition pattern (e.g., _class_DisplayServer_...)
    blocks = re.split(rf"\n\.\. _class_[^_]+_{key}_", section_text)[1:]
    
    result = {}
    for block in blocks:
        block.strip()
        if block:
            # look for a stop marker and cut off everything after it
            stop_index = block.find(".. rst-class:: classref-item-separator")
            if stop_index != -1:
                block = block[:stop_index]

            parsed = parse_doc_block(block)
            if parsed:
                result[parsed[0]] = parsed[1]

    return result

def parse_class(name: str) -> dict[str, dict[str, str]]:
    """Return structured class data with dynamic section parsing."""

    text = get_class_rst(name)

    # initialize empty dictionary to hold final class data
    class_data = {}

    # define a mapping of section keys to their corresponding header keywords
    section_mapping = {
        "enums": {
            "title": "Enumerations",
            "key": "constant"
        },
        "constants": {
            "title": "Constants",
            "key": "constant"
        },
        "properties": {
            "title": "Property Descriptions",
            "key": "property"
        },
        "methods": {
            "title": "Method Descriptions",
            "key": "method"
        },
        "signals": {
            "title": "Signals",
            "key": "signal"
        }
    }

    # for each section, call parse_section with the appropriate keyword
    for key, mapping in section_mapping.items():
        class_data[key] = parse_section(mapping["key"], mapping["title"], text)

    return class_data

def parse_globals(name: str) -> dict[str, dict[str, str]]:
    """Return structured class data with dynamic section parsing."""
    
    text = get_class_rst(name)

    # initialize empty dictionary to hold final class data
    class_data = {}

    # define a mapping of section keys to their corresponding header keywords
    section_mapping = {
        "enums": {
            "title": "Enumerations",
            "key": "constant"
        },
        "constants": {
            "title": "Constants",
            "key": "constant"
        },
        "properties": {
            "title": "Property Descriptions",
            "key": "property"
        },
        "methods": {
            "title": "Method Descriptions",
            "key": "method"
        },
        "signals": {
            "title": "Signals",
            "key": "signal"
        }
    }

    # for each section, call parse_section with the appropriate keyword
    for key, mapping in section_mapping.items():
        class_data[key] = parse_section(mapping["key"], mapping["title"], text)

    return class_data


# # https://docs.godotengine.org/en/stable/classes/class_%40globalscope.html#enumerations
# # includes
# def parse_global_scope():
    

def md_to_lua_comments(md: str) -> str:
    lines = md.splitlines()
    lua_lines = []
    previous_was_blank = False

    inside_code = False
    
    for line in lines:
        line = line.replace("\\ ", "").replace(".. tabs::", "")

        stripped = line.strip()
        is_code = stripped.startswith(".. code")
        is_rst_marker = stripped.startswith("..")

        # detect end of tabs block or other directive
        if inside_code and is_rst_marker:                
            line_count = len(lua_lines)
            if lua_lines[line_count - 1] == "---":
                lua_lines.pop(line_count - 1)
            
            inside_code = False
            lua_lines.append(f"--- ```")
            lua_lines.append(f"---")

        # detect a new code tab
        if is_code and not inside_code:
            inside_code = True
            current_lang = line.split("::", 1)[1].strip()
            lua_lines.append(f"--- ***{current_lang}***")    # '--- gdscript'
            lua_lines.append(f"--- ```{current_lang}")       # '--- ```gdscript'
            continue


        if not line:
            # preserve paragraph spacing with a single comment line``
            if not previous_was_blank:
                lua_lines.append("---")
            previous_was_blank = True
            continue

        # add regular line as Lua comment
        lua_lines.append(f"--- {line}")
        previous_was_blank = False
    
    if inside_code:
        lua_lines.append(f"--- ```")

    return "\n".join(lua_lines)


def _class_test():
    _class = "MultiplayerPeer"
    class_data = parse_class(_class)
    print(f"{_class} = {list(class_data.keys())}")
    for key, value in class_data.items():
        print(f"{key}: {len(value)}")
    
    # example_property = "get_physics_frames" #"max_fps"
    # properties = class_data["properties"]
    # # print(f"{_class}'s Properties:", list(properties.keys()))
    # print(f"\n{_class} Lua comment example for '{example_property}':\n")
    # print(md_to_lua_comments(properties[example_property]))

    # example_method = "get_physics_frames"
    # methods = class_data["methods"]
    # # print(f"{_class}'s Methods:", list(methods.keys()))
    # print(f"\n{_class} Lua comment example for '{example_method}':\n")
    # print(md_to_lua_comments(methods[example_method]))

    # example_enum = "CONNECTION_CONNECTED"
    # enums = class_data["enums"]
    # print(f"{_class}'s Enums:", list(enums.keys()))
    # print(f"\n{_class} Lua comment example for '{example_enum}':\n")
    # print(md_to_lua_comments(enums[example_enum]))

    example_signal = "peer_connected"
    signals = class_data["signals"]
    # print(f"{_class}'s Signals:", list(signals.keys()))
    print(f"\n{_class} Lua comment example for '{example_signal}':\n")
    print(md_to_lua_comments(signals[example_signal]))

def _globals_test():
    _globals = get_globals_rst()

if __name__ == "__main__":
    _class_test()
    # _globals_test()
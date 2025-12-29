import sys
import os
import io
import copy
from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Layout, Window, FormattedTextControl, HSplit, FloatContainer, Float
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.widgets import Dialog, TextArea
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import ANSI
from rich.console import Console
from rich.tree import Tree
from markdown_it import MarkdownIt

# --- Global Setup ---
console = Console(file=io.StringIO(), force_terminal=True, width=100)

class Node:
    def __init__(self, text, parent=None):
        self.text = text
        self.children = []
        self.collapsed = False
        self.parent = parent

class AppState:
    def __init__(self, filename):
        self.filename = filename
        self.root = Node(os.path.basename(filename))
        self.selected_index = 0
        self.is_editing = False
        self.status_msg = " Arrows: Nav | e: Edit | Tab: Add Child | Enter: Add Sibling | s: Save "

    def get_visible_nodes(self):
        visible = []
        def walk(node):
            visible.append(node)
            if not node.collapsed:
                for child in node.children:
                    walk(child)
        walk(self.root)
        return visible

    def get_selected_node(self):
        nodes = self.get_visible_nodes()
        self.selected_index = max(0, min(self.selected_index, len(nodes) - 1))
        return nodes[self.selected_index]

# --- Markdown Logic ---
def parse_md(md_text, filename):
    md = MarkdownIt()
    tokens = md.parse(md_text)
    root = Node(os.path.basename(filename))
    stack = [(0, root)]
    for i, token in enumerate(tokens):
        if token.type == "heading_open":
            level = int(token.tag[1])
            content = tokens[i + 1].content
            node = Node(content)
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1]
            node.parent = parent
            parent.children.append(node)
            stack.append((level, node))
    return root

def to_markdown(node, level=0):
    lines = []
    if level > 0:
        lines.append(f"{'#' * level} {node.text}")
    for child in node.children:
        lines.extend(to_markdown(child, level + 1))
    return lines

# --- State Init ---
target_file = sys.argv[1] if len(sys.argv) > 1 else "mindmap.md"
state = AppState(target_file)

# UI Elements
edit_input = TextArea(multiline=False)
edit_dialog = Dialog(
    title=lambda: "Node Text",
    body=edit_input,
    width=60
)

# --- Helpers ---
def trigger_edit(event, default_text=""):
    state.is_editing = True
    edit_input.text = default_text
    event.app.layout.focus(edit_input)

# --- Key Bindings ---
kb = KeyBindings()
is_not_editing = ~Condition(lambda: state.is_editing)
is_editing = Condition(lambda: state.is_editing)

@kb.add("q", filter=is_not_editing)
def _(event):
    event.app.exit()

@kb.add("up", filter=is_not_editing)
def _(event):
    state.selected_index -= 1

@kb.add("down", filter=is_not_editing)
def _(event):
    state.selected_index += 1

@kb.add("e", filter=is_not_editing)
def _(event):
    trigger_edit(event, state.get_selected_node().text)

@kb.add("tab", filter=is_not_editing)
def add_child_and_edit(event):
    parent = state.get_selected_node()
    new_node = Node("New Node", parent=parent)
    parent.children.append(new_node)
    parent.collapsed = False
    # Move selection to the new node
    state.selected_index = state.get_visible_nodes().index(new_node)
    trigger_edit(event, "")

@kb.add("enter", filter=is_not_editing)
def add_sibling_and_edit(event):
    current = state.get_selected_node()
    if current.parent:
        new_node = Node("New Sibling", parent=current.parent)
        idx = current.parent.children.index(current)
        current.parent.children.insert(idx + 1, new_node)
        # Move selection to the new node
        state.selected_index = state.get_visible_nodes().index(new_node)
        trigger_edit(event, "")

@kb.add("enter", filter=is_editing)
def finish_edit(event):
    state.get_selected_node().text = edit_input.text or "Untitled"
    state.is_editing = False
    event.app.layout.focus(root_window)

@kb.add("escape", filter=is_editing)
def cancel_edit(event):
    state.is_editing = False
    event.app.layout.focus(root_window)

@kb.add("d", "d", filter=is_not_editing)
def _(event):
    node = state.get_selected_node()
    if node.parent:
        node.parent.children.remove(node)

@kb.add("s", filter=is_not_editing)
def _(event):
    with open(state.filename, "w") as f:
        f.write("\n".join(to_markdown(state.root)))
    state.status_msg = f" Saved: {state.filename} "

@kb.add("space", filter=is_not_editing)
def _(event):
    node = state.get_selected_node()
    if node.children:
        node.collapsed = not node.collapsed

# --- Rendering ---
def get_ui_content():
    with console.capture() as capture:
        selected = state.get_selected_node()
        # highlight=False is key to preventing the "entire branch green" problem
        rich_tree = Tree(f" {state.root.text} ", 
                         style="reverse green" if state.root == selected else "bold magenta",
                         highlight=False)
        
        def recurse(rich_n, logic_n):
            for child in logic_n.children:
                is_sel = (child == selected)
                style = "reverse green" if is_sel else ""
                prefix = "[+] " if child.children and child.collapsed else ""
                branch = rich_n.add(f"{prefix}{child.text}", style=style)
                if not child.collapsed:
                    recurse(branch, child)
        
        recurse(rich_tree, state.root)
        console.print(rich_tree)
    return ANSI(capture.get())

# --- Layout ---
root_window = Window(content=FormattedTextControl(get_ui_content))
status_bar = Window(content=FormattedTextControl(lambda: state.status_msg), height=1, style="reverse")

body = FloatContainer(
    content=HSplit([root_window, status_bar]),
    floats=[
        Float(content=ConditionalContainer(
            content=edit_dialog,
            filter=is_editing
        ))
    ]
)

if __name__ == "__main__":
    if os.path.exists(state.filename):
        with open(state.filename, "r") as f:
            state.root = parse_md(f.read(), state.filename)
    
    Application(layout=Layout(body), key_bindings=kb, full_screen=True).run()
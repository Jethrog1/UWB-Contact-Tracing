from __future__ import annotations

import itertools
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any


class VarBase:
    def __init__(self, value: Any = None):
        self._value = value

    def get(self) -> Any:
        return self._value

    def set(self, value: Any) -> None:
        self._value = value


class BooleanVar(VarBase):
    pass


class StringVar(VarBase):
    pass


class WidgetStub:
    def __init__(self, *args: Any, **kwargs: Any):
        self.options: dict[str, Any] = {}
        self._bindings: dict[str, Any] = {}
        self.destroyed = False
        self.configure(**kwargs)

    def configure(self, **kwargs: Any) -> None:
        self.options.update(kwargs)

    config = configure

    def cget(self, key: str) -> Any:
        return self.options.get(key)

    def pack(self, *args: Any, **kwargs: Any) -> None:
        return None

    def grid(self, *args: Any, **kwargs: Any) -> None:
        return None

    def place(self, *args: Any, **kwargs: Any) -> None:
        self.options.update(kwargs)

    def lift(self, *args: Any, **kwargs: Any) -> None:
        return None

    def bind(self, event: str, handler: Any, add: Optional[str] = None) -> Any:
        self._bindings[event] = handler
        return handler

    def destroy(self) -> None:
        self.destroyed = True

    def focus_set(self) -> None:
        return None

    def select_range(self, start: int, end: int) -> None:
        return None


class HeadlessEntry(WidgetStub):
    def __init__(self, *args: Any, textvariable: Optional[VarBase] = None, **kwargs: Any):
        self.textvariable = textvariable
        super().__init__(*args, **kwargs)

    def get(self) -> str:
        if self.textvariable is None:
            return str(self.options.get("value", ""))
        return str(self.textvariable.get() or "")

    def delete(self, start: int, end: Any = None) -> None:
        if self.textvariable is not None:
            self.textvariable.set("")

    def insert(self, index: int, value: str) -> None:
        if self.textvariable is not None:
            self.textvariable.set(value)


class HeadlessLabel(WidgetStub):
    pass


class HeadlessButton(WidgetStub):
    pass


class RecordingCanvas(WidgetStub):
    def __init__(self, width: int = 800, height: int = 600):
        super().__init__()
        self.width = width
        self.height = height
        self.cursor = ""
        self.primitives: list[dict[str, Any]] = []

    def set_size(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def winfo_width(self) -> int:
        return int(self.width)

    def winfo_height(self) -> int:
        return int(self.height)

    def delete(self, what: str) -> None:
        if what == "all":
            self.primitives = []

    def configure(self, **kwargs: Any) -> None:
        super().configure(**kwargs)
        if "cursor" in kwargs:
            self.cursor = kwargs["cursor"]

    config = configure

    @staticmethod
    def _norm_points(args: tuple[Any, ...]) -> list[float]:
        if len(args) == 1 and isinstance(args[0], (list, tuple)):
            return [float(v) for v in args[0]]
        return [float(v) for v in args]

    def _append(self, kind: str, points: list[float], **options: Any) -> int:
        primitive = {"kind": kind, "points": points, "options": options}
        self.primitives.append(primitive)
        return len(self.primitives)

    def create_line(self, *args: Any, **kwargs: Any) -> int:
        return self._append("line", self._norm_points(args), **kwargs)

    def create_oval(self, *args: Any, **kwargs: Any) -> int:
        return self._append("oval", self._norm_points(args), **kwargs)

    def create_rectangle(self, *args: Any, **kwargs: Any) -> int:
        return self._append("rect", self._norm_points(args), **kwargs)

    def create_polygon(self, *args: Any, **kwargs: Any) -> int:
        return self._append("polygon", self._norm_points(args), **kwargs)

    def create_text(self, *args: Any, **kwargs: Any) -> int:
        return self._append("text", self._norm_points(args), **kwargs)

    def create_arc(self, *args: Any, **kwargs: Any) -> int:
        return self._append("arc", self._norm_points(args), **kwargs)


class TreeNode:
    __slots__ = ("iid", "parent", "text", "open", "values", "children")

    def __init__(self, iid: str, parent: str, text: str, open_: bool, values: tuple[Any, ...]):
        self.iid = iid
        self.parent = parent
        self.text = text
        self.open = open_
        self.values = values
        self.children: list[str] = []


class HeadlessTree(WidgetStub):
    def __init__(self):
        super().__init__()
        self._ids = itertools.count(1)
        self._nodes: dict[str, TreeNode] = {}
        self._roots: list[str] = []
        self._selection: list[str] = []

    def insert(self, parent: str, index: str, text: str = "", open: bool = False, values: tuple[Any, ...] = ()) -> str:
        iid = f"tree-{next(self._ids)}"
        parent_id = "" if parent in ("", None) else str(parent)
        node = TreeNode(iid, parent_id, text, bool(open), tuple(values))
        self._nodes[iid] = node
        if parent_id:
            self._nodes[parent_id].children.append(iid)
        else:
            self._roots.append(iid)
        return iid

    def delete(self, *items: str) -> None:
        if not items:
            items = tuple(self._roots)
        for item in list(items):
            self._delete_one(item)

    def _delete_one(self, iid: str) -> None:
        node = self._nodes.pop(iid, None)
        if node is None:
            return
        for child in list(node.children):
            self._delete_one(child)
        if node.parent:
            parent = self._nodes.get(node.parent)
            if parent is not None:
                parent.children = [child for child in parent.children if child != iid]
        else:
            self._roots = [root for root in self._roots if root != iid]
        self._selection = [sid for sid in self._selection if sid != iid]

    def get_children(self, item: str = "") -> tuple[str, ...]:
        if item in ("", None):
            return tuple(self._roots)
        node = self._nodes.get(str(item))
        return tuple(node.children if node else [])

    def item(self, iid: str, option: Optional[str] = None, **kwargs: Any) -> Any:
        node = self._nodes[str(iid)]
        if kwargs:
            if "text" in kwargs:
                node.text = kwargs["text"]
            if "open" in kwargs:
                node.open = bool(kwargs["open"])
            if "values" in kwargs:
                node.values = tuple(kwargs["values"])
        if option == "values":
            return node.values
        if option == "text":
            return node.text
        return {"text": node.text, "open": node.open, "values": node.values}

    def parent(self, iid: str) -> str:
        node = self._nodes.get(str(iid))
        return node.parent if node else ""

    def selection(self) -> tuple[str, ...]:
        return tuple(self._selection)

    def selection_set(self, items: str | list[str] | tuple[str, ...]) -> None:
        if isinstance(items, (list, tuple)):
            self._selection = [str(item) for item in items]
        else:
            self._selection = [str(items)]

    def export(self) -> list[dict[str, Any]]:
        def node_to_dict(iid: str) -> dict[str, Any]:
            node = self._nodes[iid]
            return {
                "id": node.iid,
                "text": node.text,
                "open": node.open,
                "values": list(node.values),
                "children": [node_to_dict(child) for child in node.children],
            }

        return [node_to_dict(root) for root in self._roots]


class HeadlessRoot(WidgetStub):
    def __init__(self):
        super().__init__()
        self.title_text = ""
        self.cursor = "arrow"
        self.tk = SimpleNamespace(call=lambda *args, **kwargs: None)

    def title(self, text: str) -> None:
        self.title_text = text

    def after(self, delay_ms: int, callback: Optional[Any] = None) -> None:
        return None

    def bind_all(self, event: str, handler: Any, add: Optional[str] = None) -> Any:
        self._bindings[event] = handler
        return handler

    def winfo_containing(self, x: int, y: int) -> None:
        return None

    def configure(self, **kwargs: Any) -> None:
        super().configure(**kwargs)
        if "cursor" in kwargs:
            self.cursor = kwargs["cursor"]

    config = configure


def notify_error(app: Any, title: str, message: str) -> None:
    if hasattr(app, "post_error"):
        app.post_error(title, message)


def notify_info(app: Any, title: str, message: str) -> None:
    if hasattr(app, "post_info"):
        app.post_info(title, message)


class _NoopStyle:
    def theme_use(self, *args: Any, **kwargs: Any) -> None:
        return None

    def configure(self, *args: Any, **kwargs: Any) -> None:
        return None

    def map(self, *args: Any, **kwargs: Any) -> None:
        return None


tk = SimpleNamespace(
    Tk=HeadlessRoot,
    Frame=WidgetStub,
    Canvas=RecordingCanvas,
    Label=HeadlessLabel,
    Button=HeadlessButton,
    Entry=HeadlessEntry,
    Checkbutton=HeadlessButton,
    StringVar=StringVar,
    BooleanVar=BooleanVar,
)

ttk = SimpleNamespace(
    Style=lambda root=None: _NoopStyle(),
    Frame=WidgetStub,
    Treeview=HeadlessTree,
    Scrollbar=WidgetStub,
)
simpledialog = SimpleNamespace(askfloat=lambda *args, **kwargs: None)


@dataclass
class MouseEvent:
    x: float
    y: float
    state: int = 0
    num: Optional[int] = None
    delta: int = 0
    button: int = 0
    x_root: int = 0
    y_root: int = 0


@dataclass
class KeyEvent:
    keysym: str
    state: int = 0

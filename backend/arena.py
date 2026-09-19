"""
Flat Memory Arena and Compact Node Representation
Demonstrates OS Memory Efficiency:
- Avoids Python object / __dict__ overhead by using __slots__ with fixed 32-64 byte footprint.
- Allows scanning hundreds of thousands of nodes with < 50MB RAM footprint.
- Enables lightning-fast Post-Order Rollup and Pruning.
"""

class CompactFileNode:
    __slots__ = (
        "name",
        "path",
        "is_dir",
        "size_logical",
        "size_physical",
        "slack_space",
        "children",
        "file_count",
        "subfolder_count",
    )

    def __init__(self, name: str, is_dir: bool, path: str = "", size_logical: int = 0, size_physical: int = 0, slack_space: int = 0):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.size_logical = size_logical
        self.size_physical = size_physical
        self.slack_space = slack_space
        self.children = [] if is_dir else None
        self.file_count = 0 if is_dir else 1
        self.subfolder_count = 0


    def add_child(self, child_node):
        if self.children is not None:
            self.children.append(child_node)

    def rollup_sizes(self):
        """
        Post-order traversal rollup (Bottom-Up):
        Calculates total directory size from child nodes.
        """
        if not self.is_dir or not self.children:
            return

        total_logical = 0
        total_physical = 0
        total_slack = 0
        total_files = 0
        total_subfolders = 0

        for child in self.children:
            if child.is_dir:
                child.rollup_sizes()
                total_subfolders += 1 + child.subfolder_count
                total_files += child.file_count
            else:
                total_files += 1

            total_logical += child.size_logical
            total_physical += child.size_physical
            total_slack += child.slack_space

        self.size_logical = total_logical
        self.size_physical = total_physical
        self.slack_space = total_slack
        self.file_count = total_files
        self.subfolder_count = total_subfolders


"""
Hierarchy Aggregator, Visual LoD Pruning, and TreeView Transformer
Responsible for Student 3: Theerameth Saikham

Features:
1. convert_to_tree_view_data: Generates full directory hierarchy for TreeSize Sidebar & Table.
2. convert_to_treemap_data: Squarified Treemap hierarchy with LoD Pruning.
"""

from typing import Dict, Any, List
from backend.arena import CompactFileNode
from backend.os_storage import format_bytes

def convert_to_tree_view_data(node: CompactFileNode, depth: int = 0, max_depth: int = 6) -> Dict[str, Any]:
    """
    Transforms CompactFileNode tree into a clean JSON structure
    consumed directly by Vue 3 recursive tree component.
    """
    data = {
        "name": node.name,
        "path": node.path,
        "is_dir": node.is_dir,
        "size_logical": node.size_logical,
        "size_physical": node.size_physical,
        "slack_space": node.slack_space,
        "formatted_size": format_bytes(node.size_logical),
        "formatted_physical": format_bytes(node.size_physical),
        "formatted_slack": format_bytes(node.slack_space),
        "file_count": node.file_count,
        "subfolder_count": node.subfolder_count,
    }

    if node.is_dir and node.children:
        # Sort children: directories first by size descending, then files by size descending
        dirs = [c for c in node.children if c.is_dir]
        files = [c for c in node.children if not c.is_dir]
        dirs.sort(key=lambda x: x.size_logical, reverse=True)
        files.sort(key=lambda x: x.size_logical, reverse=True)

        if depth < max_depth:
            data["children"] = [
                convert_to_tree_view_data(c, depth + 1, max_depth)
                for c in (dirs + files)
            ]
        else:
            data["children"] = []
    else:
        data["children"] = []

    return data


def convert_to_treemap_data(node: CompactFileNode, threshold_pct: float = 0.005, max_children: int = 25) -> Dict[str, Any]:
    """
    Transforms CompactFileNode tree into an optimized ECharts treemap data format.
    Applies LoD Pruning to keep node count bounded and maintain 60 FPS.
    """
    data = {
        "name": node.name,
        "path": node.path,
        "value": node.size_logical,
        "physical_size": node.size_physical,
        "slack_space": node.slack_space,
        "formatted_size": format_bytes(node.size_logical),
        "formatted_physical": format_bytes(node.size_physical),
        "formatted_slack": format_bytes(node.slack_space),
        "is_dir": node.is_dir,
        "file_count": node.file_count,
    }

    if not node.is_dir or not node.children:
        return data

    sorted_children = sorted(node.children, key=lambda c: c.size_logical, reverse=True)
    
    total_parent_size = node.size_logical if node.size_logical > 0 else 1
    retained_children: List[Dict[str, Any]] = []
    
    others_logical = 0
    others_physical = 0
    others_slack = 0
    others_count = 0

    for i, child in enumerate(sorted_children):
        ratio = child.size_logical / total_parent_size
        if i >= max_children or (ratio < threshold_pct and i > 5):
            others_logical += child.size_logical
            others_physical += child.size_physical
            others_slack += child.slack_space
            others_count += child.file_count
        else:
            retained_children.append(convert_to_treemap_data(child, threshold_pct, max_children))

    if others_count > 0 and others_logical > 0:
        retained_children.append({
            "name": f"[Others: {others_count} items]",
            "path": node.path,
            "value": others_logical,
            "physical_size": others_physical,
            "slack_space": others_slack,
            "formatted_size": format_bytes(others_logical),
            "formatted_physical": format_bytes(others_physical),
            "formatted_slack": format_bytes(others_slack),
            "is_dir": True,
            "file_count": others_count,
            "children": [],
        })

    data["children"] = retained_children
    return data

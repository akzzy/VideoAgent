"""
Thin wrapper around the DaVinci Resolve MCP server tools.
This module is imported by resolve_builder.py to communicate with Resolve.
"""
import sys
import os

# Add the MCP server's Python path so we can use DaVinciResolveScript
_RESOLVE_SCRIPT_DIRS = [
    os.path.join(os.getenv("PROGRAMDATA", ""), "Blackmagic Design", "DaVinci Resolve",
                 "Support", "Developer", "Scripting", "Modules"),
]

def _get_resolve():
    for d in _RESOLVE_SCRIPT_DIRS:
        if d not in sys.path and os.path.isdir(d):
            sys.path.append(d)
    try:
        import DaVinciResolveScript as dvr
        return dvr.scriptapp("Resolve")
    except Exception as e:
        raise RuntimeError(f"Cannot connect to DaVinci Resolve: {e}")


def import_timeline_xml(xml_path: str, expected_name: str) -> dict:
    """Import an FCPXML timeline into the current Resolve project."""
    resolve = _get_resolve()
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    media_pool = project.GetMediaPool()

    abs_path = os.path.abspath(xml_path)
    result = media_pool.ImportTimelineFromFile(abs_path)

    if result:
        return {"success": True, "timeline": expected_name}
    else:
        return {"success": False, "error": "ImportTimelineFromFile returned None"}

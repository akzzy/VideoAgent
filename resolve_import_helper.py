"""
Standalone script to create a DaVinci Resolve project and import a timeline XML.
Intended to be run via fuscript.exe (Resolve's built-in Python).

Usage: fuscript.exe -i py3 resolve_import_helper.py <project_name> <xml_path>
"""
import sys
import os
import time
import json

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"success": False, "error": "Usage: resolve_import_helper.py <project_name> <xml_path>"}))
        sys.exit(1)

    project_name = sys.argv[1]
    xml_path = sys.argv[2]

    if not os.path.exists(xml_path):
        print(json.dumps({"success": False, "error": f"XML not found: {xml_path}"}))
        sys.exit(1)

    try:
        import DaVinciResolveScript as dvr
    except ImportError:
        # Try adding the modules path manually
        modules_path = os.path.join(
            os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
            "Blackmagic Design", "DaVinci Resolve", "Support",
            "Developer", "Scripting", "Modules"
        )
        if os.path.isdir(modules_path) and modules_path not in sys.path:
            sys.path.append(modules_path)
        import DaVinciResolveScript as dvr

    resolve = dvr.scriptapp("Resolve")
    if not resolve:
        print(json.dumps({"success": False, "error": "Cannot connect to DaVinci Resolve. Is it running?"}))
        sys.exit(1)

    pm = resolve.GetProjectManager()
    if not pm:
        print(json.dumps({"success": False, "error": "Cannot get Project Manager"}))
        sys.exit(1)

    # Create the project (or open if exists)
    project = pm.CreateProject(project_name)
    if not project:
        # Project might already exist, try loading it
        project = pm.LoadProject(project_name)
        if not project:
            print(json.dumps({"success": False, "error": f"Cannot create or load project '{project_name}'"}))
            sys.exit(1)
        print(json.dumps({"info": f"Loaded existing project '{project_name}'"}), file=sys.stderr)

    # Import the timeline XML
    mp = project.GetMediaPool()
    if not mp:
        print(json.dumps({"success": False, "error": "Cannot get Media Pool"}))
        sys.exit(1)

    timeline = mp.ImportTimelineFromFile(xml_path)
    if timeline:
        print(json.dumps({
            "success": True,
            "project": project_name,
            "timeline": timeline.GetName(),
            "message": f"Timeline imported into project '{project_name}'"
        }))
    else:
        print(json.dumps({"success": False, "error": "Failed to import timeline XML"}))
        sys.exit(1)


if __name__ == "__main__":
    main()

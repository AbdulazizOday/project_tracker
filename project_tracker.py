from flask import Flask, render_template, request, redirect, url_for
import datetime
import os
import json

app = Flask(__name__)

# --- Configuration ---
DATA_FILE = "projects_data.json"
INACTIVITY_THRESHOLD = 3  # Days of inactivity to mark a project as stalled

# --- Helper Functions ---

def load_projects():
    """Loads project data from the JSON file."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}  # Handle empty or corrupted file
    else:
        return {}

def save_projects(projects):
    """Saves project data to the JSON file."""
    with open(DATA_FILE, "w") as f:
        json.dump(projects, f, indent=4)

def calculate_progress(project):
    """Calculates the progress percentage of a project."""
    total_tasks = len(project.get("tasks", []))
    completed_tasks = sum(1 for task in project.get("tasks", []) if task.get("completed"))  # Handle missing 'completed' key gracefully
    if total_tasks == 0:
        return 0  # Avoid division by zero
    return int((completed_tasks / total_tasks) * 100)

def is_stalled(project):
    """Checks if a project is stalled based on recent activity AND recent tasks."""
    stall_period = project.get("stall_period", 3)  # Use project-specific stall period

    # Check for recent activity
    activities = project.get("activities", [])
    last_activity_date = None
    if activities:
        last_activity_str = activities[-1].get("date")
        if last_activity_str:
            try:
                last_activity_date = datetime.datetime.strptime(last_activity_str, "%Y-%m-%d").date()
            except ValueError:  # Handle potential date parsing errors
                last_activity_date = None
    if last_activity_date:
        today = datetime.date.today()
        inactive_days = (today - last_activity_date).days
        if inactive_days < stall_period:  # Use project-specific stall period
            return False  # Recent activity, not stalled

    # Check for recent tasks (created or completed)
    tasks = project.get("tasks", [])
    if tasks:
        today = datetime.date.today()
        for task in tasks:
            created_date_str = task.get("created_date")
            completed_date_str = task.get("completed_date")

            task_date = None #Date of the most recent task activity. This can be task creation date or task completed date.

            #First check if there is a task completion date.
            if completed_date_str:
                try:
                    task_date = datetime.datetime.strptime(completed_date_str, "%Y-%m-%d").date()
                except ValueError:
                    task_date = None
            elif created_date_str: #if there is no completion date, default to creation date
                try:
                    task_date = datetime.datetime.strptime(created_date_str, "%Y-%m-%d").date()
                except ValueError:
                    task_date = None

            if(task_date):
              task_age = (today - task_date).days
              if task_age < stall_period:  # Use project-specific stall period
                  return False  # Recent task, not stalled

    # If no recent activity AND no recent tasks, then it's stalled
    return True

def sort_projects(projects):
    """Sorts projects based on priority (High > Medium > Low)."""
    priority_order = {"High": 1, "Medium": 2, "Low": 3}
    return dict(sorted(projects.items(), key=lambda item: priority_order.get(item[1].get("priority", "Low"), 4)))

# --- Routes ---

@app.route("/")
def index():
    """Displays the project progress bars and links."""
    projects = load_projects()
    active_projects = {}
    postponed_projects = {}
    cancelled_projects = {}

    for project_id, project in projects.items():
        project["progress"] = calculate_progress(project)
        if project.get("cancelled", False):
            cancelled_projects[project_id] = project
        elif project.get("postponed", False):
            postponed_projects[project_id] = project
        else:
            active_projects[project_id] = project

    active_projects = sort_projects(active_projects)
    postponed_projects = sort_projects(postponed_projects)
    cancelled_projects = sort_projects(cancelled_projects)

    return render_template(
        "index.html",
        active_projects=active_projects,
        postponed_projects=postponed_projects,
        cancelled_projects=cancelled_projects,
        is_stalled=is_stalled  # Pass the is_stalled function to the template
    )

@app.route("/add_project", methods=["GET", "POST"])
def add_project():
    """Adds a new project."""
    if request.method == "POST":
        project_name = request.form["project_name"]
        project_description = request.form["project_description"]
        project_priority = request.form["project_priority"]
        stall_period = int(request.form.get("stall_period", 3))  # Default to 3 days if not specified

        projects = load_projects()
        existing_ids = [int(pid) for pid in projects.keys() if pid.isdigit()]
        project_id = str(max(existing_ids) + 1) if existing_ids else "1"
        
        projects[project_id] = {
            "name": project_name,
            "description": project_description,
            "priority": project_priority,
            "stall_period": stall_period,  # Add stall period to project data
            "tasks": [],
            "activities": [],
        }
        save_projects(projects)
        return redirect(url_for("index"))
    return render_template("add_project.html")

@app.route("/edit_stall_period/<project_id>", methods=["GET", "POST"])
def edit_stall_period(project_id):
    """Edits the stall period for a project."""
    projects = load_projects()
    project = projects.get(project_id)
    
    if not project:
        return "Project not found", 404
        
    if request.method == "POST":
        stall_period = int(request.form["stall_period"])
        project["stall_period"] = stall_period
        save_projects(projects)
        return redirect(url_for("index"))
        
    return render_template("edit_stall_period.html", 
                         project_id=project_id, 
                         project_name=project["name"],
                         current_stall_period=project.get("stall_period", 3))

@app.route("/add_activity/<project_id>", methods=["GET", "POST"])
def add_activity(project_id):
    """Adds an activity to a project."""
    projects = load_projects()
    project = projects.get(project_id)
    if not project:
        return "Project not found", 404

    if request.method == "POST":
        activity_description = request.form["activity_description"]
        activity_date = datetime.date.today().strftime("%Y-%m-%d")  # Today's date

        if "activities" not in project:
            project["activities"] = []

        project["activities"].append({
            "date": activity_date,
            "description": activity_description,
        })
        save_projects(projects)
        return redirect(url_for("index"))

    return render_template("add_activity.html", project_id=project_id, project_name=project["name"])

@app.route("/add_task/<project_id>", methods=["GET", "POST"])
def add_task(project_id):
    """Adds a task to a project."""
    projects = load_projects()
    project = projects.get(project_id)

    if not project:
        return "Project not found", 404

    if request.method == "POST":
        task_description = request.form["task_description"]

        if "tasks" not in project:
            project["tasks"] = []

        now = datetime.datetime.now().strftime("%Y-%m-%d")
        project["tasks"].append({
            "description": task_description,
            "completed": False,
            "created_date": now, # store creation date
            "completed_date": None,
        })
        save_projects(projects)
        return redirect(url_for("index"))

    return render_template("add_task.html", project_id=project_id, project_name=project["name"])

@app.route("/complete_task/<project_id>/<task_index>")
def complete_task(project_id, task_index):
    """Marks a task as complete."""
    projects = load_projects()
    project = projects.get(project_id)

    if not project:
        return "Project not found", 404

    try:
        task_index = int(task_index)
        if 0 <= task_index < len(project.get("tasks", [])):
            project["tasks"][task_index]["completed"] = True
            project["tasks"][task_index]["completed_date"] = datetime.datetime.now().strftime("%Y-%m-%d") # record completion date
            save_projects(projects)
        else:
            return "Invalid task index", 400
    except ValueError:
        return "Invalid task index", 400

    return redirect(url_for("index"))

@app.route("/delete_project/<project_id>")
def delete_project(project_id):
    """Deletes a project."""
    projects = load_projects()
    if project_id in projects:
        del projects[project_id]
        save_projects(projects)
    return redirect(url_for("index"))

@app.route("/complete_project/<project_id>")
def complete_project(project_id):
    """Marks a project as complete."""
    projects = load_projects()
    project = projects.get(project_id)
    
    if not project:
        return "Project not found", 404
        
    project["completed"] = True
    project["completion_date"] = datetime.datetime.now().strftime("%Y-%m-%d")
    save_projects(projects)
    return redirect(url_for("index"))

@app.route("/postpone_project/<project_id>")
def postpone_project(project_id):
    """Marks a project as postponed."""
    projects = load_projects()
    project = projects.get(project_id)
    
    if not project:
        return "Project not found", 404
        
    project["postponed"] = True
    project["postponement_date"] = datetime.datetime.now().strftime("%Y-%m-%d")
    save_projects(projects)
    return redirect(url_for("index"))

@app.route("/cancel_project/<project_id>")
def cancel_project(project_id):
    """Marks a project as cancelled."""
    projects = load_projects()
    project = projects.get(project_id)
    
    if not project:
        return "Project not found", 404
        
    project["cancelled"] = True
    project["cancellation_date"] = datetime.datetime.now().strftime("%Y-%m-%d")
    save_projects(projects)
    return redirect(url_for("index"))

@app.route("/resume_project/<project_id>")
def resume_project(project_id):
    """Resumes a postponed or completed project."""
    projects = load_projects()
    project = projects.get(project_id)
    
    if not project:
        return "Project not found", 404
        
    # Remove any status flags
    project.pop("completed", None)
    project.pop("completion_date", None)
    project.pop("postponed", None)
    project.pop("postponement_date", None)
    save_projects(projects)
    return redirect(url_for("index"))

@app.route("/delete_task/<project_id>/<task_index>")
def delete_task(project_id, task_index):
    """Deletes a task from a project."""
    projects = load_projects()
    project = projects.get(project_id)

    if not project:
        return "Project not found", 404

    try:
        task_index = int(task_index)
        if 0 <= task_index < len(project.get("tasks", [])):
            project["tasks"].pop(task_index)
            save_projects(projects)
        else:
            return "Invalid task index", 400
    except ValueError:
        return "Invalid task index", 400

    return redirect(url_for("index"))

# --- Templates ---

# Create the following HTML files in a 'templates' directory:

# templates/index.html
# templates/add_project.html
# templates/add_activity.html
# templates/add_task.html

if __name__ == "__main__":
    # Ensure the data file exists on first run.
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({}, f)  # Create an empty JSON file
    app.run(debug=True)
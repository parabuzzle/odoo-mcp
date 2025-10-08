"""Projects and tasks handler for Odoo MCP."""

import logging
from mcp.types import TextContent
from .base import OdooBase

logger = logging.getLogger("odoo-mcp")


class ProjectsHandler(OdooBase):
    """Handler for project and task operations."""

    async def list_projects(self, arguments: dict) -> list[TextContent]:
        """List all projects."""
        limit = arguments.get("limit", 20)

        # Access project.project model
        Project = self.odoo.env["project.project"]

        # Search for projects
        project_ids = Project.search([], limit=limit)

        if not project_ids:
            return [TextContent(type="text", text="No projects found.")]

        # Read project details
        projects = Project.read(
            project_ids,
            ["name", "id", "user_id", "partner_id", "task_count", "active"]
        )

        # Format output
        output_lines = ["# Odoo Projects\n"]
        for project in projects:
            user_id = project.get("user_id")
            manager = user_id[1] if user_id else "Unassigned"
            partner_id = project.get("partner_id")
            partner = partner_id[1] if partner_id else "No customer"
            task_count = project.get("task_count", 0)
            active = "Active" if project.get("active", True) else "Archived"

            output_lines.append(
                f"## {project['name']} (ID: {project['id']})\n"
                f"- Status: {active}\n"
                f"- Manager: {manager}\n"
                f"- Customer: {partner}\n"
                f"- Tasks: {task_count}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

    async def get_project(self, arguments: dict) -> list[TextContent]:
        """Get a specific project by ID."""
        project_id = arguments.get("project_id")

        if not project_id:
            return [TextContent(type="text", text="Error: project_id is required")]

        # Access project.project model
        Project = self.odoo.env["project.project"]

        # Read project details
        project = Project.read(
            project_id,
            ["name", "id", "user_id", "partner_id", "task_count", "active", "description"]
        )[0]

        user_id = project.get("user_id")
        manager = user_id[1] if user_id else "Unassigned"
        partner_id = project.get("partner_id")
        partner = partner_id[1] if partner_id else "No customer"
        task_count = project.get("task_count", 0)
        active = "Active" if project.get("active", True) else "Archived"
        description = project.get("description") or "No description"

        output = (
            f"# {project['name']}\n\n"
            f"**ID:** {project['id']}  \n"
            f"**Status:** {active}  \n"
            f"**Manager:** {manager}  \n"
            f"**Customer:** {partner}  \n"
            f"**Task Count:** {task_count}  \n\n"
            f"## Description\n\n{description}"
        )

        return [TextContent(type="text", text=output)]

    async def create_project(self, arguments: dict) -> list[TextContent]:
        """Create a new project."""
        name = arguments.get("name")

        if not name:
            return [TextContent(type="text", text="Error: name is required")]

        # Build project values
        project_values = {"name": name}

        if "description" in arguments and arguments["description"]:
            project_values["description"] = arguments["description"]

        # Create the project
        Project = self.odoo.env["project.project"]
        new_project_id = Project.create(project_values)

        # Read the created project to return details
        project = Project.read(new_project_id, ["name", "id"])[0]

        output = (
            f"# Project Created Successfully\n\n"
            f"**{project['name']}** (ID: {project['id']})"
        )

        return [TextContent(type="text", text=output)]

    async def update_project(self, arguments: dict) -> list[TextContent]:
        """Update an existing project."""
        project_id = arguments.get("project_id")

        if not project_id:
            return [TextContent(type="text", text="Error: project_id is required")]

        # Build update values
        update_values = {}

        if "name" in arguments and arguments["name"]:
            update_values["name"] = arguments["name"]

        if "description" in arguments:
            update_values["description"] = arguments["description"]

        if not update_values:
            return [TextContent(type="text", text="Error: No fields to update provided")]

        # Update the project
        Project = self.odoo.env["project.project"]
        Project.write(project_id, update_values)

        # Read the updated project to return details
        project = Project.read(project_id, ["name", "id"])[0]

        output = (
            f"# Project Updated Successfully\n\n"
            f"**{project['name']}** (ID: {project['id']})"
        )

        return [TextContent(type="text", text=output)]

    async def archive_project(self, arguments: dict) -> list[TextContent]:
        """Archive a project."""
        project_id = arguments.get("project_id")

        if not project_id:
            return [TextContent(type="text", text="Error: project_id is required")]

        # Get project details before archiving
        Project = self.odoo.env["project.project"]
        project = Project.read(project_id, ["name", "id"])[0]
        project_name = project["name"]

        # Archive the project
        Project.write(project_id, {"active": False})

        output = (
            f"# Project Archived Successfully\n\n"
            f"Project **{project_name}** (ID: {project_id}) has been archived."
        )

        return [TextContent(type="text", text=output)]

    async def get_project_tasks(self, arguments: dict) -> list[TextContent]:
        """Get tasks for a specific project."""
        project_id = arguments.get("project_id")
        limit = arguments.get("limit", 50)

        if not project_id:
            return [TextContent(type="text", text="Error: project_id is required")]

        # Access project.task model
        Task = self.odoo.env["project.task"]

        # Search for tasks in this project
        task_ids = Task.search([("project_id", "=", project_id)], limit=limit)

        if not task_ids:
            return [TextContent(type="text", text=f"No tasks found in project {project_id}.")]

        # Read task details
        tasks = Task.read(
            task_ids,
            ["name", "id", "user_ids", "stage_id", "priority", "description", "date_deadline", "tag_ids"]
        )

        # Get project name
        Project = self.odoo.env["project.project"]
        project = Project.read(project_id, ["name"])[0]

        # Format output
        output_lines = [f"# Tasks in {project['name']}\n"]
        for task in tasks:
            assignees = task.get("user_ids", [])
            if assignees and len(assignees) > 0:
                # user_ids returns list of IDs, need to fetch names
                User = self.odoo.env["res.users"]
                user_names = [User.read(uid, ["name"])[0]["name"] for uid in assignees]
                assignee_str = ", ".join(user_names)
            else:
                assignee_str = "Unassigned"

            stage_id = task.get("stage_id")
            stage = stage_id[1] if stage_id else "No stage"
            priority = task.get("priority", "0")
            priority_map = {"0": "Normal", "1": "High"}
            priority_str = priority_map.get(priority, priority)
            deadline = task.get("date_deadline", "No deadline")
            description = task.get("description") or "No description"

            # Get tags
            tag_ids = task.get("tag_ids", [])
            if tag_ids and len(tag_ids) > 0:
                Tag = self.odoo.env["project.tags"]
                tag_names = [Tag.read(tag_id, ["name"])[0]["name"] for tag_id in tag_ids]
                tags_str = ", ".join(tag_names)
            else:
                tags_str = "No tags"

            output_lines.append(
                f"## {task['name']} (ID: {task['id']})\n"
                f"- Stage: {stage}\n"
                f"- Priority: {priority_str}\n"
                f"- Assigned to: {assignee_str}\n"
                f"- Deadline: {deadline}\n"
                f"- Tags: {tags_str}\n"
                f"- Description: {description}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

    async def search_tasks_by_tag(self, arguments: dict) -> list[TextContent]:
        """Search for tasks by tag name across all projects."""
        tag_name = arguments.get("tag_name")
        limit = arguments.get("limit", 50)

        if not tag_name:
            return [TextContent(type="text", text="Error: tag_name is required")]

        # Find the tag ID by name
        Tag = self.odoo.env["project.tags"]
        tag_ids = Tag.search([("name", "ilike", tag_name)], limit=1)

        if not tag_ids:
            return [TextContent(type="text", text=f"No tag found with name '{tag_name}'.")]

        tag_id = tag_ids[0]
        tag_record = Tag.read(tag_id, ["name"])[0]
        actual_tag_name = tag_record["name"]

        # Search for tasks with this tag
        Task = self.odoo.env["project.task"]
        task_ids = Task.search([("tag_ids", "in", [tag_id])], limit=limit)

        if not task_ids:
            return [TextContent(type="text", text=f"No tasks found with tag '{actual_tag_name}'.")]

        # Read task details
        tasks = Task.read(
            task_ids,
            ["name", "id", "user_ids", "stage_id", "priority", "description", "date_deadline", "tag_ids", "project_id"]
        )

        # Format output
        output_lines = [f"# Tasks with Tag: {actual_tag_name}\n"]
        for task in tasks:
            # Get project name
            project_id = task.get("project_id")
            project_name = project_id[1] if project_id else "Unknown project"

            # Get assignees
            assignees = task.get("user_ids", [])
            if assignees and len(assignees) > 0:
                User = self.odoo.env["res.users"]
                user_names = [User.read(uid, ["name"])[0]["name"] for uid in assignees]
                assignee_str = ", ".join(user_names)
            else:
                assignee_str = "Unassigned"

            # Get stage
            stage_id = task.get("stage_id")
            stage = stage_id[1] if stage_id else "No stage"

            # Get priority
            priority = task.get("priority", "0")
            priority_map = {"0": "Normal", "1": "High"}
            priority_str = priority_map.get(priority, priority)

            # Get deadline
            deadline = task.get("date_deadline", "No deadline")

            # Get description
            description = task.get("description") or "No description"

            # Get all tags for this task
            all_tag_ids = task.get("tag_ids", [])
            if all_tag_ids and len(all_tag_ids) > 0:
                tag_names = [Tag.read(tid, ["name"])[0]["name"] for tid in all_tag_ids]
                tags_str = ", ".join(tag_names)
            else:
                tags_str = "No tags"

            output_lines.append(
                f"## {task['name']} (ID: {task['id']})\n"
                f"- Project: {project_name}\n"
                f"- Stage: {stage}\n"
                f"- Priority: {priority_str}\n"
                f"- Assigned to: {assignee_str}\n"
                f"- Deadline: {deadline}\n"
                f"- Tags: {tags_str}\n"
                f"- Description: {description}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

    def _find_user_ids(self, user_names: list[str]) -> list[int]:
        """Find user IDs by name or email."""
        if not user_names:
            return []

        User = self.odoo.env["res.users"]
        user_ids = []

        for name in user_names:
            # Search for user by name or login (email) (case-insensitive)
            found_ids = User.search([
                "|",
                ("name", "ilike", name),
                ("login", "ilike", name)
            ], limit=1)
            if found_ids:
                user_ids.append(found_ids[0])
            else:
                logger.warning(f"User not found: {name}")

        return user_ids

    def _find_stage_id(self, project_id: int, stage_name: str) -> int:
        """Find stage ID by name for a specific project."""
        Stage = self.odoo.env["project.task.type"]

        # Search for stage by name in this project
        stage_ids = Stage.search([
            ("name", "ilike", stage_name),
            "|",
            ("project_ids", "=", project_id),
            ("project_ids", "=", False)  # Stages available to all projects
        ], limit=1)

        if not stage_ids:
            raise ValueError(f"Stage '{stage_name}' not found for project {project_id}")

        return stage_ids[0]

    async def create_task(self, arguments: dict) -> list[TextContent]:
        """Create a new task in a project."""
        project_id = arguments.get("project_id")
        name = arguments.get("name")

        if not project_id or not name:
            return [TextContent(type="text", text="Error: project_id and name are required")]

        # Build task values
        task_values = {
            "project_id": project_id,
            "name": name,
        }

        # Add optional fields
        if "description" in arguments and arguments["description"]:
            task_values["description"] = arguments["description"]

        # Handle assignees
        if "assignee_names" in arguments and arguments["assignee_names"]:
            user_ids = self._find_user_ids(arguments["assignee_names"])
            if user_ids:
                task_values["user_ids"] = [(6, 0, user_ids)]  # Odoo many2many replace syntax

        # Handle stage
        if "stage_name" in arguments and arguments["stage_name"]:
            stage_id = self._find_stage_id(project_id, arguments["stage_name"])
            task_values["stage_id"] = stage_id

        # Handle priority
        if "priority" in arguments:
            priority_map = {"normal": "0", "high": "1"}
            task_values["priority"] = priority_map.get(arguments["priority"], "0")

        # Handle deadline
        if "deadline" in arguments and arguments["deadline"]:
            task_values["date_deadline"] = arguments["deadline"]

        # Handle parent task (for subtasks)
        if "parent_id" in arguments and arguments["parent_id"]:
            task_values["parent_id"] = arguments["parent_id"]

        # Create the task
        Task = self.odoo.env["project.task"]
        new_task_id = Task.create(task_values)

        # Read the created task to return details
        task = Task.read(new_task_id, ["name", "id", "stage_id", "user_ids", "project_id"])[0]

        # Format output
        stage_id = task.get("stage_id")
        stage = stage_id[1] if stage_id else "No stage"

        project_id_field = task.get("project_id")
        project_name = project_id_field[1] if project_id_field else "Unknown"

        assignees = task.get("user_ids", [])
        if assignees and len(assignees) > 0:
            User = self.odoo.env["res.users"]
            user_names = [User.read(uid, ["name"])[0]["name"] for uid in assignees]
            assignee_str = ", ".join(user_names)
        else:
            assignee_str = "Unassigned"

        output = (
            f"# Task Created Successfully\n\n"
            f"**{task['name']}** (ID: {task['id']})\n"
            f"- Project: {project_name}\n"
            f"- Stage: {stage}\n"
            f"- Assigned to: {assignee_str}\n"
        )

        return [TextContent(type="text", text=output)]

    async def update_task(self, arguments: dict) -> list[TextContent]:
        """Update an existing task."""
        task_id = arguments.get("task_id")

        if not task_id:
            return [TextContent(type="text", text="Error: task_id is required")]

        # Build update values
        update_values = {}

        if "name" in arguments and arguments["name"]:
            update_values["name"] = arguments["name"]

        if "description" in arguments:
            update_values["description"] = arguments["description"]

        # Handle assignees
        if "assignee_names" in arguments:
            user_ids = self._find_user_ids(arguments["assignee_names"])
            update_values["user_ids"] = [(6, 0, user_ids)]  # Replace all assignees

        # Handle stage transition
        if "stage_name" in arguments and arguments["stage_name"]:
            # Get the task's project to find the right stage
            Task = self.odoo.env["project.task"]
            task = Task.read(task_id, ["project_id"])[0]
            project_id = task["project_id"][0] if task["project_id"] else None

            if project_id:
                stage_id = self._find_stage_id(project_id, arguments["stage_name"])
                update_values["stage_id"] = stage_id

        # Handle priority
        if "priority" in arguments:
            priority_map = {"normal": "0", "high": "1"}
            update_values["priority"] = priority_map.get(arguments["priority"], "0")

        # Handle deadline
        if "deadline" in arguments:
            update_values["date_deadline"] = arguments["deadline"] if arguments["deadline"] else False

        if not update_values:
            return [TextContent(type="text", text="Error: No fields to update provided")]

        # Update the task
        Task = self.odoo.env["project.task"]
        Task.write(task_id, update_values)

        # Read the updated task to return details
        task = Task.read(task_id, ["name", "id", "stage_id", "user_ids", "project_id", "priority", "date_deadline"])[0]

        # Format output
        stage_id = task.get("stage_id")
        stage = stage_id[1] if stage_id else "No stage"

        project_id_field = task.get("project_id")
        project_name = project_id_field[1] if project_id_field else "Unknown"

        assignees = task.get("user_ids", [])
        if assignees and len(assignees) > 0:
            User = self.odoo.env["res.users"]
            user_names = [User.read(uid, ["name"])[0]["name"] for uid in assignees]
            assignee_str = ", ".join(user_names)
        else:
            assignee_str = "Unassigned"

        priority = task.get("priority", "0")
        priority_map = {"0": "Normal", "1": "High"}
        priority_str = priority_map.get(priority, priority)

        deadline = task.get("date_deadline", "No deadline")

        output = (
            f"# Task Updated Successfully\n\n"
            f"**{task['name']}** (ID: {task['id']})\n"
            f"- Project: {project_name}\n"
            f"- Stage: {stage}\n"
            f"- Priority: {priority_str}\n"
            f"- Assigned to: {assignee_str}\n"
            f"- Deadline: {deadline}\n"
        )

        return [TextContent(type="text", text=output)]

    async def delete_task(self, arguments: dict) -> list[TextContent]:
        """Delete a task permanently."""
        task_id = arguments.get("task_id")

        if not task_id:
            return [TextContent(type="text", text="Error: task_id is required")]

        # Get task details before deletion
        Task = self.odoo.env["project.task"]
        task = Task.read(task_id, ["name", "id"])[0]
        task_name = task["name"]

        # Delete the task
        Task.unlink(task_id)

        output = (
            f"# Task Deleted Successfully\n\n"
            f"Task **{task_name}** (ID: {task_id}) has been permanently deleted."
        )

        return [TextContent(type="text", text=output)]

    async def archive_task(self, arguments: dict) -> list[TextContent]:
        """Archive a task."""
        task_id = arguments.get("task_id")

        if not task_id:
            return [TextContent(type="text", text="Error: task_id is required")]

        # Archive the task by setting active=False
        Task = self.odoo.env["project.task"]
        Task.write(task_id, {"active": False})

        # Read the archived task to return details
        task = Task.read(task_id, ["name", "id"])[0]

        output = (
            f"# Task Archived Successfully\n\n"
            f"Task **{task['name']}** (ID: {task['id']}) has been archived."
        )

        return [TextContent(type="text", text=output)]

    async def send_task_message(self, arguments: dict) -> list[TextContent]:
        """Send a message on a task."""
        task_id = arguments.get("task_id")
        body = arguments.get("body")

        if not task_id or not body:
            return [TextContent(type="text", text="Error: task_id and body are required")]

        message_type = arguments.get("message_type", "comment")

        # Get the task
        Task = self.odoo.env["project.task"]
        task_record = Task.browse(task_id)
        task_data = Task.read(task_id, ["name"])[0]

        # Handle both HTML and plain text:
        # - If body contains HTML tags, use it as-is
        # - If plain text, wrap in <p> tags and convert newlines to <br>
        if '<' not in body or '>' not in body:
            # Plain text - wrap in paragraph and convert newlines
            body = '<p>' + body.replace('\n', '<br>') + '</p>'
        # else: body already contains HTML, use as-is

        # Use message_post() with body_is_html=True to preserve HTML formatting
        # subtype_xmlid: 'mail.mt_comment' for public comments
        #                'mail.mt_note' for internal notes
        subtype_xmlid = 'mail.mt_comment' if message_type == "comment" else 'mail.mt_note'

        task_record.message_post(
            body=body,
            body_is_html=True,
            message_type=message_type,
            subtype_xmlid=subtype_xmlid
        )

        output = (
            f"# Message Sent Successfully\n\n"
            f"Message posted on task **{task_data['name']}** (ID: {task_id})\n"
            f"- Type: {message_type}\n"
        )

        return [TextContent(type="text", text=output)]

    async def get_task_messages(self, arguments: dict) -> list[TextContent]:
        """Get all messages from a task."""
        task_id = arguments.get("task_id")

        if not task_id:
            return [TextContent(type="text", text="Error: task_id is required")]

        # Get the task to find its message_ids
        Task = self.odoo.env["project.task"]
        task = Task.read(task_id, ["name", "message_ids"])[0]
        task_name = task["name"]
        message_ids = task.get("message_ids", [])

        if not message_ids:
            return [TextContent(type="text", text=f"# Messages for {task_name}\n\nNo messages found.")]

        # Read the messages
        Message = self.odoo.env["mail.message"]
        messages = Message.read(
            message_ids,
            ["id", "author_id", "body", "date", "message_type", "subtype_id"]
        )

        # Sort messages by date (oldest first)
        messages.sort(key=lambda m: m.get("date", ""))

        # Format output
        output_lines = [f"# Messages for {task_name}\n"]
        for msg in messages:
            author_id = msg.get("author_id")
            author = author_id[1] if author_id else "System"

            date = msg.get("date", "Unknown")
            message_type = msg.get("message_type", "notification")
            subtype_id = msg.get("subtype_id")
            subtype = subtype_id[1] if subtype_id else "Note"

            body = msg.get("body") or "No content"

            output_lines.append(
                f"## Message {msg['id']}\n"
                f"- **Author:** {author}\n"
                f"- **Date:** {date}\n"
                f"- **Type:** {message_type} ({subtype})\n\n"
                f"**Content:**\n{body}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

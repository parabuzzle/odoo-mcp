"""To-Do app handler for Odoo MCP."""

import logging
from mcp.types import TextContent
from .base import OdooBase

logger = logging.getLogger("odoo-mcp")


class TodosHandler(OdooBase):
    """Handler for To-Do app operations."""

    async def list_todos(self, arguments: dict) -> list[TextContent]:
        """List to-dos from the To-Do app."""
        limit = arguments.get("limit", 50)
        stage_name = arguments.get("stage")  # e.g., 'Today', 'This Week', 'Inbox'
        user_id = arguments.get("user_id")

        # Access project.task model
        Task = self.odoo.env["project.task"]

        # Build search domain for tasks without a project (To-Do app tasks)
        domain = [("project_id", "=", False)]

        if user_id:
            domain.append(("user_ids", "in", [user_id]))
        else:
            # Default to current user's tasks
            domain.append(("user_ids", "in", [self.odoo.env.uid]))

        # Filter by stage if specified
        if stage_name:
            # Find the personal stage ID by name
            Stage = self.odoo.env["project.task.type"]
            stage_ids = Stage.search([("name", "ilike", stage_name)], limit=1)
            if stage_ids:
                domain.append(("personal_stage_type_id", "=", stage_ids[0]))

        # Search for to-dos
        task_ids = Task.search(domain, limit=limit)

        if not task_ids:
            return [TextContent(type="text", text="No to-dos found.")]

        # Read task details
        tasks = Task.read(
            task_ids,
            ["name", "id", "user_ids", "personal_stage_type_id", "priority", "description", "date_deadline", "tag_ids", "state"]
        )

        # Format output
        output_lines = ["# To-Dos\n"]
        for task in tasks:
            # Get personal stage
            stage_id = task.get("personal_stage_type_id")
            stage = stage_id[1] if stage_id else "No stage"

            # Get assignees
            assignees = task.get("user_ids", [])
            if assignees and len(assignees) > 0:
                User = self.odoo.env["res.users"]
                user_names = [User.read(uid, ["name"])[0]["name"] for uid in assignees]
                assignee_str = ", ".join(user_names)
            else:
                assignee_str = "Unassigned"

            # Get priority
            priority = task.get("priority", "0")
            priority_map = {"0": "Normal", "1": "High"}
            priority_str = priority_map.get(priority, priority)

            # Get deadline
            deadline = task.get("date_deadline", "No deadline")

            # Get tags
            tag_ids = task.get("tag_ids", [])
            if tag_ids and len(tag_ids) > 0:
                Tag = self.odoo.env["project.tags"]
                tag_names = [Tag.read(tid, ["name"])[0]["name"] for tid in tag_ids]
                tags_str = ", ".join(tag_names)
            else:
                tags_str = "No tags"

            # Get description
            description = task.get("description") or "No description"

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

    async def get_todo(self, arguments: dict) -> list[TextContent]:
        """Get a specific to-do by ID."""
        todo_id = arguments.get("todo_id")

        if not todo_id:
            return [TextContent(type="text", text="Error: todo_id is required")]

        Task = self.odoo.env["project.task"]

        try:
            task = Task.read(
                todo_id,
                [
                    "id",
                    "name",
                    "description",
                    "user_ids",
                    "personal_stage_type_id",
                    "priority",
                    "date_deadline",
                    "tag_ids",
                    "project_id",
                    "state",
                    "create_date",
                    "write_date",
                    "is_closed"
                ]
            )[0]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: To-do {todo_id} not found. {str(e)}")]

        # Verify this is a to-do (no project)
        if task.get("project_id"):
            return [TextContent(type="text", text=f"Error: Task {todo_id} is not a to-do (it belongs to a project)")]

        # Format output
        stage_id = task.get("personal_stage_type_id")
        stage = stage_id[1] if stage_id else "No stage"
        stage_id_num = stage_id[0] if stage_id else "No stage ID"

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

        tag_ids = task.get("tag_ids", [])
        if tag_ids and len(tag_ids) > 0:
            Tag = self.odoo.env["project.tags"]
            tag_names = [Tag.read(tid, ["name"])[0]["name"] for tid in tag_ids]
            tags_str = ", ".join(tag_names)
        else:
            tags_str = "No tags"

        description = task.get("description") or "No description"
        create_date = task.get("create_date", "Unknown")
        write_date = task.get("write_date", "Unknown")
        state = task.get("state", "N/A")
        is_closed = task.get("is_closed", "N/A")

        output = (
            f"# To-Do: {task['name']}\n\n"
            f"**ID:** {task['id']}\n\n"
            f"**Stage:** {stage} (ID: {stage_id_num})\n\n"
            f"**State:** {state}\n\n"
            f"**is_closed:** {is_closed}\n\n"
            f"**Priority:** {priority_str}\n\n"
            f"**Assigned to:** {assignee_str}\n\n"
            f"**Deadline:** {deadline}\n\n"
            f"**Tags:** {tags_str}\n\n"
            f"**Created:** {create_date}\n\n"
            f"**Last Updated:** {write_date}\n\n"
            f"**Description:**\n{description}\n"
        )

        return [TextContent(type="text", text=output)]

    async def create_todo(self, arguments: dict) -> list[TextContent]:
        """Create a new to-do."""
        name = arguments.get("name")
        description = arguments.get("description")
        date_deadline = arguments.get("date_deadline")
        stage_name = arguments.get("stage", "Today")  # Default to "Today"
        priority = arguments.get("priority", "0")
        tag_names = arguments.get("tags", [])

        if not name:
            return [TextContent(type="text", text="Error: name is required")]

        Task = self.odoo.env["project.task"]

        # Find stage ID by name
        Stage = self.odoo.env["project.task.type"]
        stage_ids = Stage.search([("name", "ilike", stage_name)], limit=1)

        if not stage_ids:
            return [TextContent(type="text", text=f"Error: Stage '{stage_name}' not found")]

        stage_id = stage_ids[0]

        # Prepare task data
        task_data = {
            "name": name,
            "personal_stage_type_id": stage_id,
            "priority": priority,
            "user_ids": [(4, self.odoo.env.uid)],  # Assign to current user
            "project_id": False,  # No project = To-Do app
        }

        if description:
            task_data["description"] = description

        if date_deadline:
            task_data["date_deadline"] = date_deadline

        # Handle tags
        if tag_names and len(tag_names) > 0:
            Tag = self.odoo.env["project.tags"]
            tag_ids = []
            for tag_name in tag_names:
                # Search for existing tag
                existing_tag = Tag.search([("name", "=", tag_name)], limit=1)
                if existing_tag:
                    tag_ids.append(existing_tag[0])
                else:
                    # Create new tag
                    new_tag_id = Tag.create({"name": tag_name})
                    tag_ids.append(new_tag_id)
            task_data["tag_ids"] = [(6, 0, tag_ids)]

        # Create the to-do
        try:
            task_id = Task.create(task_data)
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating to-do: {str(e)}")]

        # Read back the created to-do
        task = Task.read(task_id, ["id", "name", "personal_stage_type_id", "date_deadline"])[0]

        stage = task.get("personal_stage_type_id")
        stage_name = stage[1] if stage else "Unknown"

        output = (
            f"# To-Do Created Successfully\n\n"
            f"**ID:** {task['id']}\n\n"
            f"**Name:** {task['name']}\n\n"
            f"**Stage:** {stage_name}\n\n"
            f"**Deadline:** {task.get('date_deadline', 'No deadline')}\n"
        )

        return [TextContent(type="text", text=output)]

    async def update_todo(self, arguments: dict) -> list[TextContent]:
        """Update an existing to-do."""
        todo_id = arguments.get("todo_id")
        name = arguments.get("name")
        description = arguments.get("description")
        date_deadline = arguments.get("date_deadline")
        stage_name = arguments.get("stage")
        priority = arguments.get("priority")

        if not todo_id:
            return [TextContent(type="text", text="Error: todo_id is required")]

        Task = self.odoo.env["project.task"]

        # Build update data
        update_data = {}

        if name:
            update_data["name"] = name

        if description is not None:  # Allow empty string to clear description
            update_data["description"] = description

        if date_deadline:
            update_data["date_deadline"] = date_deadline

        if priority:
            update_data["priority"] = priority

        if stage_name:
            Stage = self.odoo.env["project.task.type"]
            stage_ids = Stage.search([("name", "ilike", stage_name)], limit=1)
            if stage_ids:
                update_data["personal_stage_type_id"] = stage_ids[0]

        if not update_data:
            return [TextContent(type="text", text="Error: No fields to update")]

        # Update the to-do
        try:
            Task.write(todo_id, update_data)
        except Exception as e:
            return [TextContent(type="text", text=f"Error updating to-do: {str(e)}")]

        # Read back the updated to-do
        task = Task.read(todo_id, ["id", "name", "personal_stage_type_id", "date_deadline"])[0]

        stage = task.get("personal_stage_type_id")
        stage_name = stage[1] if stage else "Unknown"

        output = (
            f"# To-Do Updated Successfully\n\n"
            f"**ID:** {task['id']}\n\n"
            f"**Name:** {task['name']}\n\n"
            f"**Stage:** {stage_name}\n\n"
            f"**Deadline:** {task.get('date_deadline', 'No deadline')}\n"
        )

        return [TextContent(type="text", text=output)]

    async def mark_todo_done(self, arguments: dict) -> list[TextContent]:
        """Mark a to-do as done."""
        todo_id = arguments.get("todo_id")

        if not todo_id:
            return [TextContent(type="text", text="Error: todo_id is required")]

        Task = self.odoo.env["project.task"]
        Stage = self.odoo.env["project.task.type"]

        # Find Done stage with folded=True and sequence around 5-7
        done_stage_ids = Stage.search([("name", "ilike", "done"), ("fold", "=", True)])

        if not done_stage_ids:
            done_stage_ids = Stage.search([("name", "ilike", "done")])

        if not done_stage_ids:
            return [TextContent(type="text", text="Error: Could not find a 'Done' stage.")]

        # Read stages and find one with sequence 5-7
        done_stages = Stage.read(done_stage_ids, ["id", "sequence", "fold"])
        preferred_stage = None
        for stage in done_stages:
            if stage.get("fold") and 5 <= stage.get("sequence", 0) <= 7:
                preferred_stage = stage["id"]
                break

        if not preferred_stage:
            # Fallback to first folded Done stage
            for stage in done_stages:
                if stage.get("fold"):
                    preferred_stage = stage["id"]
                    break

        if not preferred_stage:
            preferred_stage = done_stages[0]["id"]

        # Move task to Done stage and mark as done
        try:
            Task.write(todo_id, {
                "personal_stage_type_id": preferred_stage,
                "state": "1_done"
            })
        except Exception as e:
            return [TextContent(type="text", text=f"Error marking to-do as done: {str(e)}")]

        # Read back the task
        task = Task.read(todo_id, ["id", "name", "personal_stage_type_id", "state", "is_closed"])[0]

        stage = task.get("personal_stage_type_id")
        stage_name = stage[1] if stage else "Unknown"

        output = (
            f"# To-Do Marked as Done\n\n"
            f"**ID:** {task['id']}\n\n"
            f"**Name:** {task['name']}\n\n"
            f"**Stage:** {stage_name}\n\n"
            f"**State:** {task.get('state')}\n\n"
            f"**is_closed:** {task.get('is_closed')}\n"
        )

        return [TextContent(type="text", text=output)]

    async def delete_todo(self, arguments: dict) -> list[TextContent]:
        """Delete a to-do."""
        todo_id = arguments.get("todo_id")

        if not todo_id:
            return [TextContent(type="text", text="Error: todo_id is required")]

        Task = self.odoo.env["project.task"]

        # Get task name before deleting
        try:
            task = Task.read(todo_id, ["name"])[0]
            task_name = task["name"]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: To-do {todo_id} not found. {str(e)}")]

        # Delete the task
        try:
            Task.unlink(todo_id)
        except Exception as e:
            return [TextContent(type="text", text=f"Error deleting to-do: {str(e)}")]

        output = f"# To-Do Deleted\n\nTo-do **{task_name}** (ID: {todo_id}) has been deleted."

        return [TextContent(type="text", text=output)]

    async def list_todo_stages(self, arguments: dict) -> list[TextContent]:
        """List available to-do stages."""
        Stage = self.odoo.env["project.task.type"]

        # Search for all stages
        # Note: Personal stages might have a specific field to identify them
        # For now, we'll list all stages
        stage_ids = Stage.search([])

        if not stage_ids:
            return [TextContent(type="text", text="No stages found.")]

        stages = Stage.read(stage_ids, ["id", "name", "sequence", "fold"])

        output_lines = ["# To-Do Stages\n"]
        for stage in sorted(stages, key=lambda x: x.get("sequence", 0)):
            name = stage.get("name", "Unknown")
            fold = stage.get("fold", False)
            fold_str = "Yes" if fold else "No"

            output_lines.append(
                f"## {name} (ID: {stage['id']})\n"
                f"- Sequence: {stage.get('sequence', 0)}\n"
                f"- Folded: {fold_str}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

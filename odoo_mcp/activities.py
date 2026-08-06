"""Activities (To-dos) handler for Odoo MCP."""

import logging
from mcp.types import TextContent
from .base import OdooBase

logger = logging.getLogger("odoo-mcp")


class ActivitiesHandler(OdooBase):
    """Handler for activity/to-do operations."""

    async def list_activities(self, arguments: dict) -> list[TextContent]:
        """List activities (to-dos)."""
        limit = arguments.get("limit", 50)
        user_id = arguments.get("user_id")
        state = arguments.get("state")  # 'overdue', 'today', 'planned', 'done'
        activity_type = arguments.get("activity_type")  # e.g., 'To-do', 'Call', 'Email', 'Meeting'

        # Access mail.activity model
        Activity = self.odoo.env["mail.activity"]

        # Build search domain
        domain = []

        if user_id:
            domain.append(("user_id", "=", user_id))

        if state:
            domain.append(("state", "=", state))

        if activity_type:
            # Find activity type ID
            ActivityType = self.odoo.env["mail.activity.type"]
            type_ids = ActivityType.search([("name", "ilike", activity_type)], limit=1)
            if type_ids:
                domain.append(("activity_type_id", "=", type_ids[0]))

        # Search for activities
        activity_ids = Activity.search(domain, limit=limit)

        if not activity_ids:
            return [TextContent(type="text", text="No activities found.")]

        # Read activity details
        activities = self.safe_read_records(
            "mail.activity",
            activity_ids,
            [
                "id",
                "summary",
                "note",
                "date_deadline",
                "user_id",
                "activity_type_id",
                "res_model",
                "res_id",
                "res_name",
                "state",
                "create_date"
            ]
        )

        # Format output
        output_lines = ["# Activities\n"]
        for activity in activities:
            activity_type = activity.get("activity_type_id")
            type_name = activity_type[1] if activity_type else "Unknown"

            user = activity.get("user_id")
            user_name = user[1] if user else "Unassigned"

            deadline = activity.get("date_deadline", "No deadline")
            state_val = activity.get("state", "planned")
            summary = activity.get("summary") or "No summary"
            note = activity.get("note") or "No description"

            # Get linked record info
            res_model = activity.get("res_model", "")
            res_name = activity.get("res_name", "")
            linked_to = f"{res_name} ({res_model})" if res_name else "Not linked"

            output_lines.append(
                f"## {summary} (ID: {activity['id']})\n"
                f"- Type: {type_name}\n"
                f"- Assigned to: {user_name}\n"
                f"- Deadline: {deadline}\n"
                f"- State: {state_val}\n"
                f"- Linked to: {linked_to}\n"
                f"- Description: {note}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

    async def get_activity(self, arguments: dict) -> list[TextContent]:
        """Get a specific activity by ID."""
        activity_id = arguments.get("activity_id")

        if not activity_id:
            return [TextContent(type="text", text="Error: activity_id is required")]

        Activity = self.odoo.env["mail.activity"]

        try:
            activity = self.safe_read_records(
                "mail.activity",
                activity_id,
                [
                    "id",
                    "summary",
                    "note",
                    "date_deadline",
                    "user_id",
                    "activity_type_id",
                    "res_model",
                    "res_id",
                    "res_name",
                    "state",
                    "create_date",
                    "create_uid"
                ]
            )[0]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: Activity {activity_id} not found. {str(e)}")]

        # Format output
        activity_type = activity.get("activity_type_id")
        type_name = activity_type[1] if activity_type else "Unknown"

        user = activity.get("user_id")
        user_name = user[1] if user else "Unassigned"

        created_by = activity.get("create_uid")
        created_by_name = created_by[1] if created_by else "Unknown"

        deadline = activity.get("date_deadline", "No deadline")
        state_val = activity.get("state", "planned")
        summary = activity.get("summary") or "No summary"
        note = activity.get("note") or "No description"
        create_date = activity.get("create_date", "Unknown")

        # Get linked record info
        res_model = activity.get("res_model", "")
        res_name = activity.get("res_name", "")
        linked_to = f"{res_name} ({res_model})" if res_name else "Not linked"

        output = (
            f"# Activity: {summary}\n\n"
            f"**ID:** {activity['id']}\n\n"
            f"**Type:** {type_name}\n\n"
            f"**Assigned to:** {user_name}\n\n"
            f"**Deadline:** {deadline}\n\n"
            f"**State:** {state_val}\n\n"
            f"**Linked to:** {linked_to}\n\n"
            f"**Created by:** {created_by_name}\n\n"
            f"**Created on:** {create_date}\n\n"
            f"**Description:**\n{note}\n"
        )

        return [TextContent(type="text", text=output)]

    async def create_activity(self, arguments: dict) -> list[TextContent]:
        """Create a new activity."""
        summary = arguments.get("summary")
        note = arguments.get("note")
        date_deadline = arguments.get("date_deadline")
        user_id = arguments.get("user_id")
        activity_type_name = arguments.get("activity_type", "To-do")
        res_model = arguments.get("res_model", "res.users")
        res_id = arguments.get("res_id")

        if not summary:
            return [TextContent(type="text", text="Error: summary is required")]

        Activity = self.odoo.env["mail.activity"]

        # Find activity type ID
        ActivityType = self.odoo.env["mail.activity.type"]
        type_ids = ActivityType.search([("name", "ilike", activity_type_name)], limit=1)
        if not type_ids:
            return [TextContent(type="text", text=f"Error: Activity type '{activity_type_name}' not found")]

        activity_type_id = type_ids[0]

        # If no user specified, use current user
        if not user_id:
            user_id = self.odoo.env.uid

        # If no res_id specified and model is res.users, use the assigned user
        if not res_id and res_model == "res.users":
            res_id = user_id

        # Get res_model_id
        Model = self.odoo.env["ir.model"]
        model_ids = Model.search([("model", "=", res_model)], limit=1)
        if not model_ids:
            return [TextContent(type="text", text=f"Error: Model '{res_model}' not found")]

        res_model_id = model_ids[0]

        # Prepare activity data
        activity_data = {
            "summary": summary,
            "activity_type_id": activity_type_id,
            "user_id": user_id,
            "res_model_id": res_model_id,
            "res_id": res_id,
        }

        if note:
            activity_data["note"] = note

        if date_deadline:
            activity_data["date_deadline"] = date_deadline

        # Create the activity
        try:
            activity_id = Activity.create(activity_data)
        except Exception as e:
            return [TextContent(type="text", text=f"Error creating activity: {str(e)}")]

        # Read back the created activity
        activity = self.safe_read_records("mail.activity", activity_id, ["id", "summary", "user_id", "date_deadline"])[0]

        user = activity.get("user_id")
        user_name = user[1] if user else "Unknown"

        output = (
            f"# Activity Created Successfully\n\n"
            f"**ID:** {activity['id']}\n\n"
            f"**Summary:** {activity['summary']}\n\n"
            f"**Assigned to:** {user_name}\n\n"
            f"**Deadline:** {activity.get('date_deadline', 'No deadline')}\n"
        )

        return [TextContent(type="text", text=output)]

    async def update_activity(self, arguments: dict) -> list[TextContent]:
        """Update an existing activity."""
        activity_id = arguments.get("activity_id")
        summary = arguments.get("summary")
        note = arguments.get("note")
        date_deadline = arguments.get("date_deadline")
        user_id = arguments.get("user_id")
        activity_type_name = arguments.get("activity_type")

        if not activity_id:
            return [TextContent(type="text", text="Error: activity_id is required")]

        Activity = self.odoo.env["mail.activity"]

        # Build update data
        update_data = {}

        if summary:
            update_data["summary"] = summary

        if note is not None:  # Allow empty string to clear note
            update_data["note"] = note

        if date_deadline:
            update_data["date_deadline"] = date_deadline

        if user_id:
            update_data["user_id"] = user_id

        if activity_type_name:
            ActivityType = self.odoo.env["mail.activity.type"]
            type_ids = ActivityType.search([("name", "ilike", activity_type_name)], limit=1)
            if type_ids:
                update_data["activity_type_id"] = type_ids[0]

        if not update_data:
            return [TextContent(type="text", text="Error: No fields to update")]

        # Update the activity
        try:
            Activity.write(activity_id, update_data)
        except Exception as e:
            return [TextContent(type="text", text=f"Error updating activity: {str(e)}")]

        # Read back the updated activity
        activity = self.safe_read_records("mail.activity", activity_id, ["id", "summary", "user_id", "date_deadline"])[0]

        user = activity.get("user_id")
        user_name = user[1] if user else "Unknown"

        output = (
            f"# Activity Updated Successfully\n\n"
            f"**ID:** {activity['id']}\n\n"
            f"**Summary:** {activity['summary']}\n\n"
            f"**Assigned to:** {user_name}\n\n"
            f"**Deadline:** {activity.get('date_deadline', 'No deadline')}\n"
        )

        return [TextContent(type="text", text=output)]

    async def mark_activity_done(self, arguments: dict) -> list[TextContent]:
        """Mark an activity as done."""
        activity_id = arguments.get("activity_id")
        feedback = arguments.get("feedback")

        if not activity_id:
            return [TextContent(type="text", text="Error: activity_id is required")]

        Activity = self.odoo.env["mail.activity"]

        try:
            # Get the activity record
            activity_record = Activity.browse(activity_id)

            # Mark as done using action_feedback method
            if feedback:
                activity_record.action_feedback(feedback=feedback)
            else:
                activity_record.action_done()
        except Exception as e:
            return [TextContent(type="text", text=f"Error marking activity as done: {str(e)}")]

        output = f"# Activity Marked as Done\n\nActivity {activity_id} has been marked as done."

        return [TextContent(type="text", text=output)]

    async def delete_activity(self, arguments: dict) -> list[TextContent]:
        """Delete an activity."""
        activity_id = arguments.get("activity_id")

        if not activity_id:
            return [TextContent(type="text", text="Error: activity_id is required")]

        Activity = self.odoo.env["mail.activity"]

        # Get activity summary before deleting
        try:
            activity = Activity.read(activity_id, ["summary"])[0]
            activity_summary = activity["summary"]
        except Exception as e:
            return [TextContent(type="text", text=f"Error: Activity {activity_id} not found. {str(e)}")]

        # Delete the activity
        try:
            Activity.unlink(activity_id)
        except Exception as e:
            return [TextContent(type="text", text=f"Error deleting activity: {str(e)}")]

        output = f"# Activity Deleted\n\nActivity **{activity_summary}** (ID: {activity_id}) has been deleted."

        return [TextContent(type="text", text=output)]

    async def list_activity_types(self, arguments: dict) -> list[TextContent]:
        """List available activity types."""
        ActivityType = self.odoo.env["mail.activity.type"]

        type_ids = ActivityType.search([])

        if not type_ids:
            return [TextContent(type="text", text="No activity types found.")]

        types = self.safe_read_records("mail.activity.type", type_ids, ["id", "name", "summary", "delay_count", "delay_unit"])

        output_lines = ["# Activity Types\n"]
        for activity_type in types:
            name = activity_type.get("name", "Unknown")
            summary = activity_type.get("summary", "")
            delay_count = activity_type.get("delay_count", 0)
            delay_unit = activity_type.get("delay_unit", "days")

            output_lines.append(
                f"## {name} (ID: {activity_type['id']})\n"
                f"- Summary: {summary}\n"
                f"- Default deadline: {delay_count} {delay_unit}\n"
            )

        return [TextContent(type="text", text="\n".join(output_lines))]

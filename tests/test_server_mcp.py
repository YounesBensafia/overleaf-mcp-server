import base64
import io
import json
import os
import unittest
from contextlib import redirect_stderr
from typing import cast
from unittest.mock import Mock, patch

from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import TextContent
from pydantic import ValidationError

from overleaf_mcp import server
from overleaf_mcp.config import Config
from overleaf_mcp.server import mcp


class TestMcpServer(unittest.IsolatedAsyncioTestCase):
    async def test_run_scrubs_runtime_and_regular_exceptions(self):
        client = Mock()
        client.scrub.return_value = "scrubbed"
        with patch.object(server, "get_client", return_value=client):
            for exception in (RuntimeError("secret"), ValueError("secret")):
                with self.assertRaisesRegex(RuntimeError, "scrubbed"):
                    await server._run(self._raise, exception)

        self.assertEqual(client.scrub.call_count, 2)

    async def test_run_scrubs_permission_error_token_forms(self):
        token = "permission-token"
        encoded = base64.b64encode(f"git:{token}".encode()).decode()
        client = Mock()
        client.scrub.side_effect = lambda text: text.replace(token, "***").replace(encoded, "***")
        with (
            patch.object(server, "get_client", return_value=client),
            self.assertRaises(RuntimeError) as raised,
        ):
            await server._run(
                self._raise,
                PermissionError(f"{token} {encoded}"),
            )

        self.assertNotIn(token, str(raised.exception))
        self.assertNotIn(encoded, str(raised.exception))

    @staticmethod
    def _raise(exception):
        raise exception

    def test_main_reports_missing_fields_to_stderr(self):
        with patch.dict(os.environ, {}, clear=True):
            try:
                Config(_env_file=None)
            except ValidationError as error:
                missing_error = error
            else:
                self.fail("Expected a validation error")

        stderr = io.StringIO()
        with (
            patch.object(server, "get_client", side_effect=missing_error),
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as raised,
        ):
            server.main()

        self.assertEqual(raised.exception.code, 1)
        self.assertIn("Missing configuration", stderr.getvalue())
        self.assertIn("OVERLEAF_TOKEN", stderr.getvalue())

    async def test_list_tools(self):
        tools = await mcp.list_tools()
        tool_names = [tool.name for tool in tools]
        self.assertEqual(
            tool_names,
            ["list_files", "read_file", "write_file", "edit_file", "sync_project"],
        )

        annotations = {tool.name: tool.annotations for tool in tools}
        list_annotations = annotations["list_files"]
        read_annotations = annotations["read_file"]
        write_annotations = annotations["write_file"]
        edit_annotations = annotations["edit_file"]
        sync_annotations = annotations["sync_project"]
        self.assertIsNotNone(list_annotations)
        self.assertIsNotNone(read_annotations)
        self.assertIsNotNone(write_annotations)
        self.assertIsNotNone(edit_annotations)
        self.assertIsNotNone(sync_annotations)
        assert list_annotations is not None
        assert read_annotations is not None
        assert write_annotations is not None
        assert edit_annotations is not None
        assert sync_annotations is not None
        self.assertTrue(list_annotations.readOnlyHint)
        self.assertTrue(read_annotations.readOnlyHint)
        self.assertFalse(write_annotations.readOnlyHint)
        self.assertTrue(write_annotations.destructiveHint)
        self.assertTrue(write_annotations.idempotentHint)
        self.assertTrue(edit_annotations.destructiveHint)
        self.assertFalse(edit_annotations.idempotentHint)
        self.assertFalse(sync_annotations.readOnlyHint)
        self.assertFalse(sync_annotations.destructiveHint)
        self.assertTrue(sync_annotations.idempotentHint)

        read_tool = next(tool for tool in tools if tool.name == "read_file")
        read_properties = read_tool.inputSchema["properties"]
        self.assertEqual(read_properties["offset"]["minimum"], 0)
        limit_schema = next(
            item for item in read_properties["limit"]["anyOf"] if item.get("type") == "integer"
        )
        self.assertEqual(limit_schema["minimum"], 1)
        self.assertEqual(limit_schema["maximum"], 10_000)

    async def test_call_list_files(self):
        with patch("overleaf_mcp.server.get_client") as get_client:
            get_client.return_value.list_files.return_value = ["main.tex"]
            result = await mcp.call_tool("list_files", {"project_id": "abc123"})

        content, structured = result
        payload = json.loads(cast(list[TextContent], content)[0].text)
        self.assertEqual(payload, ["main.tex"])
        self.assertEqual(structured, {"result": '[\n  "main.tex"\n]'})

    async def test_call_sync_project(self):
        with patch("overleaf_mcp.server.get_client") as get_client:
            get_client.return_value.ensure_repo.return_value = "/tmp/overleaf_repos/abc123"
            result = await mcp.call_tool("sync_project", {"project_id": "abc123"})

        content, structured = result
        self.assertIn("Synchronized Overleaf project", cast(list[TextContent], content)[0].text)
        self.assertEqual(structured, {"result": "Synchronized Overleaf project"})

    async def test_call_read_file(self):
        with patch("overleaf_mcp.server.get_client") as get_client:
            get_client.return_value.read_file.return_value = "file content"
            result = await mcp.call_tool(
                "read_file", {"file_path": "main.tex", "project_id": "abc123"}
            )

        content, structured = result
        self.assertEqual(cast(list[TextContent], content)[0].text, "file content")
        self.assertEqual(structured, {"result": "file content"})

    async def test_read_file_rejects_invalid_ranges_at_tool_boundary(self):
        invalid_ranges = [
            {"file_path": "main.tex", "offset": -1},
            {"file_path": "main.tex", "limit": 0},
            {"file_path": "main.tex", "limit": 10_001},
        ]
        for arguments in invalid_ranges:
            with self.subTest(arguments=arguments), self.assertRaises(ToolError):
                await mcp.call_tool("read_file", arguments)

    async def test_call_write_file(self):
        mock_result = "Updated 'main.tex' and pushed to Overleaf"
        with patch("overleaf_mcp.server.get_client") as get_client:
            get_client.return_value.write_file.return_value = mock_result
            result = await mcp.call_tool(
                "write_file",
                {"file_path": "main.tex", "content": "hello", "project_id": "abc123"},
            )

        content, structured = result
        self.assertIn("pushed to Overleaf", cast(list[TextContent], content)[0].text)
        self.assertEqual(structured, {"result": mock_result})

    async def test_call_edit_file(self):
        with patch("overleaf_mcp.server.get_client") as get_client:
            get_client.return_value.edit_file.return_value = "Updated 'main.tex'"
            result = await mcp.call_tool(
                "edit_file",
                {
                    "file_path": "main.tex",
                    "old_text": "old",
                    "new_text": "new",
                    "project_id": "abc123",
                },
            )

        content, structured = result
        self.assertEqual(cast(list[TextContent], content)[0].text, "Updated 'main.tex'")
        self.assertEqual(structured, {"result": "Updated 'main.tex'"})

    async def test_call_unknown_tool_raises(self):
        with self.assertRaises(ToolError):
            await mcp.call_tool("nonexistent", {})


if __name__ == "__main__":
    unittest.main()

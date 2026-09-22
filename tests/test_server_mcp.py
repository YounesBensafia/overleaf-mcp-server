import json
import unittest
from unittest.mock import patch

from mcp.server.fastmcp.exceptions import ToolError

from src.mcp_server import mcp


class TestMcpServer(unittest.IsolatedAsyncioTestCase):
    async def test_list_tools(self):
        tools = await mcp.list_tools()
        tool_names = [tool.name for tool in tools]
        self.assertEqual(tool_names, ["list_files", "read_file", "write_file", "sync_project"])

        annotations = {tool.name: tool.annotations for tool in tools}
        self.assertTrue(annotations["list_files"].readOnlyHint)
        self.assertTrue(annotations["read_file"].readOnlyHint)
        self.assertFalse(annotations["write_file"].readOnlyHint)
        self.assertTrue(annotations["write_file"].destructiveHint)
        self.assertFalse(annotations["sync_project"].readOnlyHint)
        self.assertTrue(annotations["sync_project"].destructiveHint)

    async def test_call_list_files(self):
        with patch("src.mcp_server.client.list_files", return_value=["main.tex"]):
            result = await mcp.call_tool("list_files", {"project_id": "abc123"})

        content, structured = result
        payload = json.loads(content[0].text)
        self.assertEqual(payload, ["main.tex"])
        self.assertEqual(structured, {"result": '[\n  "main.tex"\n]'})

    async def test_call_sync_project(self):
        with patch("src.mcp_server.client.ensure_repo", return_value="/tmp/overleaf_repos/abc123"):
            result = await mcp.call_tool("sync_project", {"project_id": "abc123"})

        content, structured = result
        self.assertIn("Synchronized Overleaf project", content[0].text)
        self.assertEqual(structured, {"result": "Synchronized Overleaf project"})

    async def test_call_read_file(self):
        with patch("src.mcp_server.client.read_file", return_value="file content"):
            result = await mcp.call_tool(
                "read_file", {"file_path": "main.tex", "project_id": "abc123"}
            )

        content, structured = result
        self.assertEqual(content[0].text, "file content")
        self.assertEqual(structured, {"result": "file content"})

    async def test_call_write_file(self):
        mock_result = "Updated 'main.tex' and pushed to Overleaf"
        with patch("src.mcp_server.client.write_file", return_value=mock_result):
            result = await mcp.call_tool(
                "write_file",
                {"file_path": "main.tex", "content": "hello", "project_id": "abc123"},
            )

        content, structured = result
        self.assertIn("pushed to Overleaf", content[0].text)
        self.assertEqual(structured, {"result": mock_result})

    async def test_call_unknown_tool_raises(self):
        with self.assertRaises(ToolError):
            await mcp.call_tool("nonexistent", {})


if __name__ == "__main__":
    unittest.main()

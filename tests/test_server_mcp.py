import json
import unittest
from unittest.mock import patch

from src.mcp_server import call_tool, list_tools


class TestMcpServer(unittest.IsolatedAsyncioTestCase):
    async def test_list_tools(self):
        tools = await list_tools()
        tool_names = [tool.name for tool in tools]
        self.assertEqual(tool_names, ["list_files", "read_file", "write_file", "sync_project"])

    async def test_call_list_files(self):
        with patch("src.mcp_server.client.list_files", return_value=["main.tex"]):
            result = await call_tool("list_files", {"project_id": "abc123"})

        payload = json.loads(result[0].text)
        self.assertEqual(payload, ["main.tex"])

    async def test_call_sync_project(self):
        with patch("src.mcp_server.client.ensure_repo", return_value="/tmp/overleaf_repos/abc123"):
            result = await call_tool("sync_project", {"project_id": "abc123"})

        self.assertIn("Synchronized Overleaf project", result[0].text)

    async def test_call_read_file(self):
        with patch("src.mcp_server.client.read_file", return_value="file content"):
            result = await call_tool("read_file", {"file_path": "main.tex", "project_id": "abc123"})

        self.assertEqual(result[0].text, "file content")

    async def test_call_write_file(self):
        mock_result = "Updated 'main.tex' and pushed to Overleaf"
        with patch("src.mcp_server.client.write_file", return_value=mock_result):
            result = await call_tool(
                "write_file",
                {"file_path": "main.tex", "content": "hello", "project_id": "abc123"},
            )

        self.assertIn("pushed to Overleaf", result[0].text)

    async def test_call_unknown_tool_raises(self):
        with self.assertRaises(ValueError):
            await call_tool("nonexistent", {})


if __name__ == "__main__":
    unittest.main()

import json
import os
import subprocess
import sys
import unittest


class TestStdioSmoke(unittest.TestCase):
    def test_tools_list_over_stdio(self):
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "smoke-test", "version": "0.1"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        ]
        environment = os.environ.copy()
        environment.update(
            {
                "OVERLEAF_TOKEN": "smoke-test-token",
                "PROJECT_ID": "0123456789abcdef01234567",
            }
        )
        completed = subprocess.run(
            [sys.executable, "-m", "overleaf_mcp.server"],
            input="\n".join(json.dumps(message) for message in messages) + "\n",
            text=True,
            capture_output=True,
            env=environment,
            check=True,
            timeout=10,
        )

        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        tools_response = next(response for response in responses if response.get("id") == 2)
        tool_names = {tool["name"] for tool in tools_response["result"]["tools"]}
        self.assertEqual(
            tool_names,
            {"list_files", "read_file", "write_file", "edit_file", "sync_project"},
        )


if __name__ == "__main__":
    unittest.main()

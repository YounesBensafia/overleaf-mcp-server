import asyncio
import json
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_overleaf_mcp():
    # Configure server parameters
    # Assumes the server is in src/main.py and PYTHONPATH is set to workspace root
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "src/main.py"],
        env={
            **os.environ,
            "PYTHONPATH": ".",
            "OVERLEAF_TOKEN": os.getenv("OVERLEAF_TOKEN", "test_token"),
            "PROJECT_ID": os.getenv("PROJECT_ID", "test_project")
        }
    )

    print("Connecting to Overleaf MCP server...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the session
            await session.initialize()
            print("Successfully initialized session.")

            # 1. List available tools
            print("\n--- Listing Tools ---")
            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"- {tool.name}: {tool.description}")

            # 2. Test Tool: fetch_project_files
            print("\n--- Testing tool: fetch_project_files ---")
            project_id = os.getenv("PROJECT_ID", "your_project_id")
            try:
                result = await session.call_tool("fetch_project_files", {"project_id": project_id})
                print(f"Result: {result.content[0].text}")
                
                # If we have files, try to read the first one for the next test
                import ast
                files = ast.literal_eval(result.content[0].text)
                target_file = files[0] if files else "main.tex"
            except Exception as e:
                print(f"Error calling fetch_project_files: {e}")
                target_file = "main.tex"

            # 3. Test Tool: read_latex_file
            print(f"\n--- Testing tool: read_latex_file ({target_file}) ---")
            try:
                result = await session.call_tool("read_latex_file", {
                    "project_id": project_id, 
                    "file_path": target_file
                })
                print(f"Result: {result.content[0].text[:100]}...") # Print first 100 chars
            except Exception as e:
                print(f"Error calling read_latex_file: {e}")

            # 4. Test Tool: write_latex_file
            print("\n--- Testing tool: write_latex_file ---")
            try:
                result = await session.call_tool("write_latex_file", {
                    "project_id": project_id, 
                    "file_path": "mcp_test.tex",
                    "content": "% Test file created by MCP server\n\\section{MCP Test}"
                })
                print(f"Result: {result.content[0].text}")
            except Exception as e:
                print(f"Error calling write_latex_file: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(test_overleaf_mcp())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Test failed: {e}")

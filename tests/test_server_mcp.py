import asyncio
import json
import os
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Load .env file
load_dotenv()

async def test_latex_mcp():
    """Test the LaTeX MCP server in local mode."""
    
    # Use a test project directory
    test_project = "/tmp/latex_test_project"
    os.makedirs(test_project, exist_ok=True)
    
    # Create a test main.tex if it doesn't exist
    main_tex = os.path.join(test_project, "main.tex")
    if not os.path.exists(main_tex):
        with open(main_tex, 'w') as f:
            f.write(r"""\documentclass{article}
\begin{document}
\section{Test}
Hello World!
\end{document}
""")
    
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "src/main.py"],
        env={
            **os.environ,
            "PYTHONPATH": ".",
            "MODE": "local",
            "PROJECT_PATH": test_project,
        }
    )

    print("Connecting to LaTeX MCP server...")
    print(f"Project path: {test_project}\n")
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("✓ Connected successfully\n")

            # 1. List tools
            print("--- Available Tools ---")
            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"  • {tool.name}")
            print()

            # 2. List files
            print("--- list_files ---")
            result = await session.call_tool("list_files", {})
            files = json.loads(result.content[0].text)
            print(f"  Files: {files}\n")

            # 3. Read file
            print("--- read_file ---")
            result = await session.call_tool("read_file", {"file_path": "main.tex"})
            content = result.content[0].text
            print(f"  Content preview: {content[:80]}...\n")

            # 4. Write file
            print("--- write_file ---")
            result = await session.call_tool("write_file", {
                "file_path": "chapter1.tex",
                "content": "\\section{Chapter 1}\nThis was created by the MCP server."
            })
            print(f"  Result: {result.content[0].text}\n")

            # 5. Get outline
            print("--- get_outline ---")
            result = await session.call_tool("get_outline", {})
            outline = json.loads(result.content[0].text)
            print(f"  Outline: {json.dumps(outline, indent=4)}\n")

            # 6. Compile (if pdflatex available)
            print("--- compile ---")
            result = await session.call_tool("compile", {"main_file": "main.tex"})
            compile_result = json.loads(result.content[0].text)
            print(f"  Status: {compile_result.get('status')}")
            if compile_result.get('errors'):
                print(f"  Errors: {compile_result['errors']}")
            print()

            print("✓ All tests completed!")

if __name__ == "__main__":
    try:
        asyncio.run(test_latex_mcp())
    except KeyboardInterrupt:
        print("\nTest interrupted")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()

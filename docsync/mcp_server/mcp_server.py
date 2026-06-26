"""
mcp_server.py — MCP Server for Clinical Document Intelligence Pipeline.

Exposes one tool to any MCP-compatible client (Claude Desktop, Cursor):
  - ingest_document : Run OCR ingestion on scanned clinical documents

Usage:
    python mcp/mcp_server.py

Cursor MCP config (~/.cursor/mcp.json):
    {
      "mcpServers": {
        "clinical-doc-pipeline": {
          "command": "python",
          "args": ["C:/Users/lahar/OneDrive/Desktop/clinical-doc-pipeline/docsync/mcp/mcp_server.py"]
        }
      }
    }
"""

import asyncio
import io
import json
import os
import sys
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("clinical-doc-pipeline")

PENDING_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "qa", "review", "pending"
)


def count_pending():
    if not os.path.exists(PENDING_DIR):
        return 0
    return len([f for f in os.listdir(PENDING_DIR) if f.endswith(".json")])


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="ingest_document",
            description=(
                "Ingest scanned clinical documents using Azure Document Intelligence OCR. "
                "Extracts text, scores confidence per document, and automatically routes "
                "low-confidence documents to the QA review queue for human inspection. "
                "Supports scanned prior auth forms, EOBs, discharge summaries, and "
                "handwritten clinical notes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "enum": [
                            "prebuilt-read",
                            "prebuilt-layout",
                            "prebuilt-document"
                        ],
                        "description": (
                            "Azure DI model to use:\n"
                            "  prebuilt-read     — plain scanned text\n"
                            "  prebuilt-layout   — forms with tables/checkboxes (prior auth, EOBs)\n"
                            "  prebuilt-document — key-value forms (claims attachments)"
                        ),
                        "default": "prebuilt-layout"
                    }
                },
                "required": []
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "ingest_document":
        model = arguments.get("model", "prebuilt-layout")

        try:
            from connectors.scanned_pdf_connector import run as run_scanned

            f = io.StringIO()
            with redirect_stdout(f):
                run_scanned(model=model)
            output = f.getvalue()

            pending = count_pending()
            result = {
                "status": "success",
                "model_used": model,
                "pipeline_output": output,
                "qa_pending": pending,
                "message": (
                    f"Ingestion complete. {pending} document(s) flagged for QA review. "
                    f"Run 'python qa/qa_manager.py' to review."
                    if pending > 0
                    else "Ingestion complete. All documents passed QA confidence threshold."
                )
            }

        except Exception as e:
            result = {
                "status": "error",
                "error": str(e)
            }

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    return [TextContent(type="text", text=json.dumps({
        "status": "error",
        "error": f"Unknown tool: {name}"
    }))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
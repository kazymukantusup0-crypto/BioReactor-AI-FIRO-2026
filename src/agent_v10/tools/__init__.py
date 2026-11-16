"""Calculation tools of agent v10. Every number the agent shows comes from here.

Each tool returns a ToolResult-like dict:
    name         tool name
    ok           True if something was calculated
    data         full result (for the dashboard cards and charts)
    llm          compact result: only key rounded numbers and labels (for the LLM)
    assumptions  list of human-readable assumptions in the user's language
    sources      list of literature sources {id, title, year, doi, url}
    label        "measured" | "literature" | "assumption" (weakest input wins)
    question     at most ONE clarifying question, or None
"""

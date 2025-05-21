# agents/task_tool.py

from langchain_core.tools import tool
from TaskCreationAgent import intent_and_board_agent, task_extractor_agent, generate_report


@tool
def task_agent() -> str:
    """
    Smart Trello assistant: handles task creation or reporting based on user intent.
    """
    print("📝 [Tool] Task assistant ready.")
    user_input = input("🗣️ Describe what you want to do (e.g., 'create tasks', 'generate a report'):\n")

    result = intent_and_board_agent(user_input)

    if result.user_intention == "create_task" and result.board:
        return task_extractor_agent(result.board, user_input)
    elif result.user_intention == "generate_report" and result.board:
        return generate_report(result.board)
    else:
        return f"🤖 {result.AiResponse}"

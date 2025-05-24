import os
import google.generativeai as genai
from dotenv import load_dotenv
from langgraph.graph import Graph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage
from utils.state import AgentState

# Agents
from agents.contract_tool import create_contract
from agents.meeting_tool import schedule_meeting
from agents.document_tool import document_organizer
from agents.task_tool import task_agent

# Env + Gemini
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")

# Register tools
tools = [create_contract, schedule_meeting, document_organizer, task_agent]
tool_node = ToolNode(tools=tools)

# Main agent (intent classifier)
def call_model(state: AgentState) -> AgentState:
    messages = state["messages"]
    user_input = messages[-1].content.strip()

    intent_prompt = f"""
You are an intent classification assistant. Based on the user's message, respond ONLY with one of the following intents:
- schedule_meeting
- create_contract
- document_organizer
- task_agent
- general_query

User message: \"{user_input}\"

Your answer:
"""
    intent = model.generate_content(intent_prompt).text.strip().lower()

    if "schedule_meeting" in intent:
        return {"messages": [AIMessage(content="", tool_calls=[{
            "name": "schedule_meeting", "args": {}, "id": "call_schedule_meeting"
        }])]}
    elif "create_contract" in intent:
        return {"messages": [AIMessage(content="", tool_calls=[{
            "name": "create_contract", "args": {}, "id": "call_create_contract"
        }])]}
    elif "document_organizer" in intent:
        return {"messages": [AIMessage(content="", tool_calls=[{
            "name": "document_organizer", "args": {}, "id": "call_document_organizer"
        }])]}
    elif "task_agent" in intent:
        return {"messages": [AIMessage(content="", tool_calls=[{
            "name": "task_agent", "args": {}, "id": "call_task_agent"
        }])]}
    else:
        response = model.generate_content(user_input)
        return {"messages": [AIMessage(content=response.text)]}

# Check if another tool should be triggered
def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    return "continue" if getattr(last_message, "tool_calls", None) else "end"

# Build graph
workflow = Graph()
workflow.set_entry_point("agent")
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)
workflow.add_conditional_edges("agent", should_continue, {
    "continue": "tools",
    "end": END
})
workflow.add_edge("tools", "agent")

# Compile
app = workflow.compile()

import os
import google.generativeai as genai
from dotenv import load_dotenv
from langgraph.graph import Graph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage, AIMessage
from utils.state import AgentState
from agents.contract_tool import create_contract
from agents.meeting_tool import schedule_meeting

# ✅ Load environment variables
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# ✅ Use Gemini 2.0 Flash model
model = genai.GenerativeModel("gemini-2.0-flash")

# ✅ Register tool agents
tools = [create_contract, schedule_meeting]
tool_node = ToolNode(tools=tools)

# ✅ Model logic: detect intent and trigger tool or respond
def call_model(state: AgentState) -> AgentState:
    messages = state["messages"]
    user_input = messages[-1].content.strip()

    # Intent classification prompt
    intent_prompt = f"""
You are an intent classification assistant. Based on the user's message, respond ONLY with one of the following intents:
- schedule_meeting
- create_contract
- general_query

User message: \"{user_input}\"

Your answer:
"""
    intent_response = model.generate_content(intent_prompt).text.strip().lower()

    # 🔁 Trigger appropriate tool
    if "schedule_meeting" in intent_response:
        return {"messages": [
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "schedule_meeting",
                    "args": {},  # ✅ dict not string
                    "id": "tool_call_schedule_meeting"
                }]
            )
        ]}
    elif "create_contract" in intent_response:
        return {"messages": [
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "create_contract",
                    "args": {},  # ✅ dict not string
                    "id": "tool_call_create_contract"
                }]
            )
        ]}
    else:
        # 🧠 General response from Gemini
        response = model.generate_content(user_input)
        return {"messages": [AIMessage(content=response.text)]}

# ✅ Determine if tool should run or exit
def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "continue"
    return "end"

# ✅ Build LangGraph
workflow = Graph()
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {
    "continue": "tools",
    "end": END
})
workflow.add_edge("tools", "agent")

# ✅ Compile LangGraph
app = workflow.compile()
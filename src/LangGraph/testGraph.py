import os
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from src.ContractAgent import main as contract_main
from src.SchedulingAgent import MeetingSchedulingAgent
from src.DocumentOrganizationAgent import DocumentIntelligencePipeline
from src.TaskCreation_And_Progress_report_Agent import intent_and_board_agent, task_extractor_agent, generate_report

from google.generativeai import GenerativeModel
import google.generativeai as genai

# === Load environment variables ===
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# === Set your API Key for Gemini ===
genai.configure(api_key=api_key)
model = GenerativeModel(model_name="gemini-2.0-flash")


# === Intent Classifier Node ===
def intent_classifier(state: dict):
    user_input = state["user_input"]

    prompt = (
        f"Classify the following user request into one of these categories:\n"
        f"1. Contract Creation\n"
        f"2. Meeting Scheduling\n"
        f"3. Task Management\n"
        f"4. Document Organization\n"
        f"5. Greeting or Help Request\n"
        f"If the intention is unclear or does not fit any category, respond with 'Unknown'.\n\n"
        f"User Input: \"{user_input}\"\n\n"
        f"Respond ONLY with one of these words: Contract, Meeting, Task, Document, Greeting, Unknown."
    )

    response = model.generate_content(prompt)
    classification = response.text.strip().lower()

    if "contract" in classification:
        return {"next": "contract_agent"}
    elif "meeting" in classification:
        return {"next": "meeting_agent"}
    elif "task" in classification:
        return {"next": "task_agent"}
    elif "document" in classification:
        return {"next": "document_agent"}
    elif "greeting" in classification:
        return {"next": "greeting_handler"}
    else:
        return {"next": "unknown_handler"}


# === Contract Agent Node ===
def contract_agent(state: dict):
    print("📝 Contract Agent Running")
    contract_main()
    return {"result": "✅ Contract Created!"}


# === Meeting Agent Node ===
def meeting_agent(state: dict):
    print("📅 Meeting Agent Selected.")
    scheduler = MeetingSchedulingAgent()
    scheduler.run()
    return {"result": "✅ Meeting scheduled!"}


# === Task Agent Node ===
def task_agent(state: dict):
    print("🗂️ Task Agent Activated.")
    user_input = state["user_input"]

    parsed = intent_and_board_agent(user_input)

    if parsed.user_intention == "create_task":
        print(f"📋 Creating tasks on board: {parsed.board}")
        result = task_extractor_agent(parsed.board, user_input)
        return {"result": f"✅ Tasks created:\n{result}"}

    elif parsed.user_intention == "generate_report":
        print(f"📊 Generating report for board: {parsed.board}")
        report = generate_report(parsed.board)
        return {"result": f"📄 Report:\n{report}"}

    else:
        return {"result": "🤝 Let me know what you'd like to do with your tasks!"}


# === Document Agent Node ===
def document_agent(state: dict):
    print("📂 Document Agent Selected.")
    doc_agent = DocumentIntelligencePipeline()
    doc_agent.run()
    return {"result": "✅ Document processed and stored!"}


# === Greeting Handler Node ===
def greeting_handler(state: dict):
    print("👋 Hello! I'm your smart assistant.")
    return {
        "result": (
            "💡 You can ask me to:\n"
            "- Create contracts\n"
            "- Schedule meetings\n"
            "- Manage Trello tasks\n"
            "- Organize and search documents\n"
            "How can I help you today?"
        )
    }


# === Unknown Input Node ===
def unknown_handler(state: dict):
    user_input = state.get("user_input", "")
    print(f"❓ I’m not sure what you meant by: \"{user_input}\"")
    return {
        "result": (
            "⚠️ I couldn't understand your request.\n"
            "💡 Try something like:\n"
            "- 'Create a contract for hiring'\n"
            "- 'Schedule a meeting with Ali tomorrow at 3PM'\n"
            "- 'Add tasks to the Marketing board'\n"
            "- 'Process this document file'\n"
        )
    }


# === Build the Graph ===
graph = StateGraph(dict)

graph.add_node("intent_classifier", intent_classifier)
graph.add_node("contract_agent", contract_agent)
graph.add_node("meeting_agent", meeting_agent)
graph.add_node("task_agent", task_agent)
graph.add_node("document_agent", document_agent)
graph.add_node("greeting_handler", greeting_handler)
graph.add_node("unknown_handler", unknown_handler)

graph.set_entry_point("intent_classifier")

graph.add_conditional_edges(
    "intent_classifier",
    lambda x: x["next"],
    {
        "contract_agent": "contract_agent",
        "meeting_agent": "meeting_agent",
        "task_agent": "task_agent",
        "document_agent": "document_agent",
        "greeting_handler": "greeting_handler",
        "unknown_handler": "unknown_handler",
    }
)

graph.add_edge("contract_agent", END)
graph.add_edge("meeting_agent", END)
graph.add_edge("task_agent", END)
graph.add_edge("document_agent", END)
graph.add_edge("greeting_handler", END)
graph.add_edge("unknown_handler", END)

# === Compile and Run ===
app = graph.compile()

if __name__ == "__main__":
    user_input = input("🖐️ Hi! Please enter your request: ")
    initial_state = {"user_input": user_input}
    result = app.invoke(initial_state)
    print("\n🎯 Final Result:", result["result"])

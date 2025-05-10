# testGraph.py

from langgraph.graph import StateGraph, END
from ..testContract import main as contract_main
from ..testSmartScheduale import MeetingSchedulingAgent
from ..DocumentOrganizationAgent import DocumentIntelligencePipeline
from google.generativeai import GenerativeModel
import google.generativeai as genai

# Set your API Key for Gemini
genai.configure(api_key="")

# Create Gemini model client
model = GenerativeModel(model_name="gemini-2.0-flash")

# === Intent Classifier Node ===
def intent_classifier(state: dict):
    user_input = state["user_input"]

    prompt = (
        f"Classify the following user request into one of three categories:\n"
        f"1. Contract Creation\n"
        f"2. Meeting Scheduling\n"
        f"3. Document Organization\n\n"
        f"User Input: \"{user_input}\"\n\n"
        f"Respond ONLY with one of these words: Contract, Meeting, Document."
    )

    response = model.generate_content(prompt)
    classification = response.text.strip().lower()

    if "contract" in classification:
        return {"next": "contract_agent"}
    elif "meeting" in classification:
        return {"next": "meeting_agent"}
    elif "document" in classification:
        return {"next": "document_agent"}
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

# === Document Agent Node ===
def document_agent(state: dict):
    print("📂 Document Agent Selected.")
    doc_agent = DocumentIntelligencePipeline()
    file_path = input("📄 Please provide the full path to your document: ").strip()
    doc_agent.process_and_store(file_path)
    return {"result": "✅ Document processed and stored!"}

# === Unknown Input Node ===
def unknown_handler(state: dict):
    print("❓ Sorry, I couldn't understand your request.")
    return {"result": "⚠️ Unknown request."}

# === Build the Graph ===
graph = StateGraph(dict)

graph.add_node("intent_classifier", intent_classifier)
graph.add_node("contract_agent", contract_agent)
graph.add_node("meeting_agent", meeting_agent)
graph.add_node("document_agent", document_agent)
graph.add_node("unknown_handler", unknown_handler)

graph.set_entry_point("intent_classifier")

graph.add_conditional_edges(
    "intent_classifier",
    lambda x: x["next"],
    {
        "contract_agent": "contract_agent",
        "meeting_agent": "meeting_agent",
        "document_agent": "document_agent",
        "unknown_handler": "unknown_handler",
    }
)

graph.add_edge("contract_agent", END)
graph.add_edge("meeting_agent", END)
graph.add_edge("document_agent", END)
graph.add_edge("unknown_handler", END)

# === Compile and Run ===
app = graph.compile()

if __name__ == "__main__":
    user_input = input("🖐️ Hi! Please enter your request: ")
    initial_state = {"user_input": user_input}
    result = app.invoke(initial_state)
    print("\n🎯 Final Result:", result["result"])

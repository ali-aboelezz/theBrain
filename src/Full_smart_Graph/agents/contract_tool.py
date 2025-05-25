import os
from uuid import uuid4
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.messages import ToolMessage
import google.generativeai as genai

from agents.testContract import ContractGenerator, pick_template_file

# Load Gemini API key
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")


@tool
def create_contract() -> ToolMessage:
    """
    Smart contract tool: detects if user wants a single or multiple contracts,
    prompts accordingly, and handles both paths.
    """
    print("\n🤖 Would you like to generate a single contract or multiple?")
    user_input = input("🧑 You: ").strip().lower()

    if user_input in ["exit", "cancel", "stop", "nothing", "no", "thank you", "nothing else"]:
        return ToolMessage(
            content="👋 Got it. No contract will be created. Ask me anything when you're ready.",
            name="create_contract",
            tool_call_id="tool_call_create_contract"
        )

    # Gemini-based intent classification
    intent_prompt = f"""
You are a smart intent classifier. Classify the user's intent as "single" or "multiple".

Input: "{user_input}"

Rules:
- If user wants to create one contract (e.g. "just one", "a contract", "only one"): return single
- If user wants to create many (e.g. "many", "batch", "a few", "several", "docs", "templates"): return multiple
- Output only one word: single or multiple
"""
    try:
        intent_raw = model.generate_content(intent_prompt).text.strip().lower()
        intent = intent_raw.split()[0]
    except Exception:
        intent = "unknown"

    # Fallback keyword matching
    if intent not in ["single", "multiple"]:
        if any(word in user_input for word in ["many", "multiple", "batch", "docs", "a few", "several"]):
            intent = "multiple"
        elif any(word in user_input for word in ["one", "just", "single", "a contract"]):
            intent = "single"
        else:
            return ToolMessage(
                content="❓ I couldn't determine if you want to generate one or many contracts. Try saying 'one' or 'many'.",
                name="create_contract",
                tool_call_id="tool_call_create_contract"
            )

    print(f"[DEBUG] User input classified as → {intent}")

    if intent == "single":
        return handle_single_contract()
    else:
        return handle_multiple_contracts()


def handle_single_contract() -> ToolMessage:
    print("\n📂 Please choose the contract template file (.docx)")
    template_path = pick_template_file()

    if not template_path or not os.path.exists(template_path):
        return ToolMessage(
            content="❌ No valid template was selected. Please try again and choose a `.docx` file.",
            name="create_contract",
            tool_call_id="create_contract"
        )

    name_tag = uuid4().hex[:4]
    output_path = f"contract_output_{name_tag}.docx"
    contract_type = os.path.basename(template_path).split('.')[0]

    generator = ContractGenerator(template_path, output_path, contract_type)

    print("🔍 Extracting placeholders from the template...")
    generator.extract_placeholders()

    print("🤖 Generating questions...")
    questions = generator.generate_questions()

    print("🧠 Please answer the following:")
    generator.collect_responses(questions)

    print("✍️ Filling in the document...")
    generator.fill_document()

    print("📄 Exporting PDF...")
    generator.export_to_pdf(output_path.replace(".docx", ".pdf"))

    return ToolMessage(
        content=(
            f"✅ Contract generated!\n\n"
            f"📄 DOCX: `{output_path}`\n"
            f"📑 PDF: `{output_path.replace('.docx', '.pdf')}`\n\n"
            f"💬 Ask me something else or type 'exit' to quit."
        ),
        name="create_contract",
        tool_call_id="create_contract"
    )


def handle_multiple_contracts() -> ToolMessage:
    print("\n📂 Please choose the contract template file (.docx) for multiple generation")
    template_path = pick_template_file()

    if not template_path or not os.path.exists(template_path):
        return ToolMessage(
            content="❌ No valid template was selected. Please try again and choose a `.docx` file.",
            name="create_contract",
            tool_call_id="create_contract"
        )

    output_path = f"bulk_output_{uuid4().hex[:4]}.docx"
    contract_type = os.path.basename(template_path).split('.')[0]

    generator = ContractGenerator(template_path, output_path, contract_type)

    print("📊 Generating Excel sheet for bulk input...")
    generator.handle_multiple_documents()

    print("✅ All documents have been generated successfully.")

    # ✅ Important: Do NOT re-trigger contract tool again — we're done
    return ToolMessage(
        content=(
            "✅ All contracts generated successfully.\n\n"
            "📄 Excel-based batch processing complete.\n"
            "💬 Let me know if you'd like to create more, or type 'exit' to finish."
        ),
        name="create_contract",
        tool_call_id="create_contract"
    )

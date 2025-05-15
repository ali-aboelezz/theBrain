import os
import uuid
from datetime import datetime

from langchain import LLMChain, PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pymilvus import MilvusClient
import google.generativeai as genai

#from utils.text_extractor import TextImgExtractor

from utils.send_mail import send_email
from config.config import FilePaths

from dotenv import load_dotenv
load_dotenv()

FILE_PATHS = FilePaths()

class DocumentIntelligencePipeline:
    
    """
    DocumentIntelligencePipeline

    A comprehensive pipeline that automates document processing using OCR, text classification,
    summarization, semantic search, and notification functionalities.

    Key Functionalities:
    ---------------------
    1. OCR (Optical Character Recognition):
        - Extracts text from image-based documents using PaddleOCR.
        - Supports various image formats such as PNG, JPG, JPEG, BMP, and TIFF.

    2. Text Classification & Summarization:
        - Classifies documents into categories (e.g., "Email", "Invoice", etc.) using Google Gemini LLM.
        - Generates a brief summary of the document using another Gemini-based LLM chain.

    3. Semantic Embedding & Storage:
        - Generates semantic embeddings for document text using Google’s embedding model.
        - Stores document metadata, content, embeddings, and summaries in Milvus vector database.
        - Automatically creates the Milvus collection if it does not exist.

    4. Semantic Search:
        - Accepts user queries and returns the most relevant stored documents using vector similarity.

    5. Email Notification:
        - Sends an email notification when a new document is processed and categorized.
        - Uses SMTP protocol with predefined Gmail credentials.

    Components:
    -----------
    - PaddleOCR: For extracting text from images.
    - Google Gemini API: For document classification and summarization.
    - Milvus: For storing and searching document vectors.
    - SMTP: For email alerts to notify about processed document types.

    Methods:
    --------
    - extract_text_from_image(image_path): Extracts text from image files using PaddleOCR.
    - analyze_document(text): Uses Gemini to classify and summarize document content.
    - process_and_store(file_path): Complete pipeline to extract, analyze, embed, and store a document.
    - send_email_notification(email, document_name, category): Notifies the user via email of the document's category.
    - milvus_search(question): Accepts a natural language query and retrieves the most relevant document from the Milvus DB.

    Usage Example:
    --------------
    >>> pipeline = DocumentIntelligencePipeline()
    >>> pipeline.process_and_store("invoice.png")
    >>> results = pipeline.milvus_search("show me my job applications")
    >>> print(results)

    This class enables automated document workflows for intelligent search, retrieval, and alerting.
    Ideal for use cases in digital archives, document management systems, and enterprise automation.

    
    """

    def __init__(self):
        self.milvus_db_path = FILE_PATHS.milvus_db_path
        self._setup_gemini_api()
        self._setup_milvus()
        self.col_name = "documents_collection"
       # self.text_extractor = TextImgExtractor(engine="paddleocr")
        self.from_email = os.getenv("SENDER_EMAIL")  # used in send_email()

    def _setup_gemini_api(self):
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0,
            max_tokens=500,
            timeout=None,
            max_retries=2,
            seed=42,
            verbose=False
        )

    def _setup_milvus(self):
        self.milvus_client = MilvusClient(self.milvus_db_path)

    """
    def extract_text_from_image(self, image_path):
        return self.text_extractor.extract_text_paddleocr(image_path)   """

    def analyze_document(self, text):
        classification_prompt = PromptTemplate(
            input_variables=["text"],
            template="""
                  classify the provided document into *one of the predefined categories only*. 

                  Strict Instructions:
                  - Choose ONLY from the following categories: [email, invoice, report, legal, resume, article, non-sense, other]
                  - If the text is meaningless, empty, or random characters, classify it as *non-sense*
                  - If you can not determine exactly the category, classify it as *other*
                  - DO NOT invent new categories
                  - DO NOT add explanation — return only the category in lowercase

                  Examples:
                  1. "Dear Hiring Manager, I am applying for the data science position..."  
                    → email

                  2. "asdf asdf jkljlkj"  
                    → non-sense

                  Text to classify: {text}
                  """
        )

        classify_chain = LLMChain(llm=self.llm, prompt=classification_prompt, output_key="document_category")

        summary_prompt = PromptTemplate(
            input_variables=["text", "document_category"],
            template="""<s><|user|>
            Summarize the key points from this {text} lengthy document with the category {document_category}.
            Use only two sentences.<|end|> <|assistant|>"""
        )

        summary_chain = LLMChain(llm=self.llm, prompt=summary_prompt, output_key="summary")

        result = classify_chain.invoke({"text": text})
        category = result["document_category"].strip()

        summary = summary_chain.invoke({"text": text, "document_category": category})["summary"].strip()

        return {"document_category": category, "summary": summary}
    
    def notify_user(self, to_email, document_name, category):
        subject = "New Document Categorized"
        message = f"Document: {document_name} has been categorized as '{category}'."
        print(f"📩 Email Notification Sent: {message}")
        return send_email(self.from_email, to_email, subject, message)

    def extract_metadata(self, path):
        return os.path.basename(path), os.path.splitext(path)[1]

    def process_and_store(self, file_paths, receiver_email=None):
        if isinstance(file_paths, str):
            file_paths = [file_paths]

        for file_path in file_paths:
            ext = os.path.splitext(file_path)[1].lower()
            is_image = ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff']

            if is_image:
                text = self.extract_text_from_image(file_path)
            else:
                with open(file_path, 'rb') as f:
                    text = f.read().decode("latin-1")

            analysis = self.analyze_document(text)
            category, summary = analysis["document_category"], analysis["summary"]

            if category.lower() == "non-sense":
                print(f"⚠️  {file_path} → 'non-sense'. Skipping.")
                continue

            if category.lower() == "other":
                print(f"⚠️  {file_path} → 'other'. Please enter the correct category manually.")
                category = input("Enter correct category: ").strip().lower()

            file_name, file_format = self.extract_metadata(file_path)
            vector = genai.embed_content(model="models/text-embedding-004", content=text)["embedding"]
            doc_id = int(uuid.uuid4().int % (2**63))

            if not self.milvus_client.has_collection(collection_name=self.col_name):
                self.milvus_client.create_collection(
                    collection_name=self.col_name,
                    dimension=len(vector),
                    metric_type="IP",
                    consistency_level="Strong"
                )

            res = self.milvus_client.insert(
                collection_name=self.col_name,
                data=[{
                    "id": doc_id,
                    "vector": vector,
                    "category": category,
                    "summary": summary,
                    "file_name": file_name,
                    "file_format": file_format,
                    "document": text,
                    "date": datetime.now().isoformat()
                }]
            )

            print(f"✅ Stored {file_name} (Category: {category}) ")

            # Optional email notification
            if receiver_email:
                self.notify_user(receiver_email, file_name, category)
    def search_documents(self, question):
        embedding = genai.embed_content(model="models/text-embedding-004", content=question)["embedding"]
        result = self.milvus_client.search(
            collection_name=self.col_name,
            data=[embedding],
            limit=1,
            search_params={"metric_type": "IP", "params": {}},
            output_fields=["document"]
        )
        return result

    def run(self):
        """Interactive CLI to process documents and optionally send notifications."""
        print("\n===== Document Intelligence Pipeline =====")
        print("Smart OCR | Classification | Summarization | Search | Notification")
        print("==========================================")

        while True:
            print("\nWhat would you like to do?")
            print("1. Process new document(s)")
            print("2. Smart search")
            print("3. Exit")

            choice = input("\nEnter your choice (1-3): ")

            if choice == "1":
                file_input = input("Enter file paths (comma-separated if multiple): ").strip()
                file_paths = [path.strip() for path in file_input.split(",") if path.strip()]
                email = input("Enter notification email (or press Enter to skip): ").strip()
                email = email if email else None
                self.process_and_store(file_paths, email)

            elif choice == "2":
                query = input("\nEnter your search query:\n")
                results = self.search_documents(query)
                print("\nTop Result:")
                if results and results[0]:
                    print(results[0][0]["document"])
                else:
                    print("No results found.")

            elif choice == "3":
                print("\nThank you for using the Document Intelligence Pipeline. Goodbye!")
                break

            else:
                print("\nInvalid choice. Please try again.")


# Run the pipeline if executed as a script
if __name__ == "__main__":
    pipeline = DocumentIntelligencePipeline()
    pipeline.run()
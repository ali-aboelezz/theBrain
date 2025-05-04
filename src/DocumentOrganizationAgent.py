import os
import torch
import uuid
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from utils.text_extractor import TextImgExtractor

from langchain import LLMChain, PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pymilvus import MilvusClient
import google.generativeai as genai

class DocumentIntelligencePipeline:
    """
    DocumentIntelligencePipeline

    A comprehensive pipeline that automates document processing using OCR, text classification,
    summarization, semantic search, and notification functionalities.

    Key Functionalities:
    ---------------------
    1. *OCR (Optical Character Recognition)*:
        - Extracts text from image-based documents using PaddleOCR.
        - Supports various image formats such as PNG, JPG, JPEG, BMP, and TIFF.

    2. *Text Classification & Summarization*:
        - Classifies documents into categories (e.g., "Email", "Invoice", etc.) using Google Gemini LLM.
        - Generates a brief summary of the document using another Gemini-based LLM chain.

    3. *Semantic Embedding & Storage*:
        - Generates semantic embeddings for document text using Google’s embedding model.
        - Stores document metadata, content, embeddings, and summaries in Milvus vector database.
        - Automatically creates the Milvus collection if it does not exist.

    4. *Semantic Search*:
        - Accepts user queries and returns the most relevant stored documents using vector similarity.

    5. *Email Notification*:
        - Sends an email notification when a new document is processed and categorized.
        - Uses SMTP protocol with predefined Gmail credentials.

    Components:
    -----------
    - *PaddleOCR*: For extracting text from images.
    - *Google Gemini API*: For document classification and summarization.
    - *Milvus*: For storing and searching document vectors.
    - *SMTP*: For email alerts to notify about processed document types.

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
        # === Setup APIs and Models ===
        self._setup_gemini_api()
        self._setup_email()
        self._setup_milvus()
        self.col_name = "documents_collection"
        self.text_extractor = TextImgExtractor(engine="paddleocr")

    def _setup_gemini_api(self):
        os.environ["GOOGLE_API_KEY"] = '' #need to add Gemini API Key
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
        self.llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0, max_tokens=500, timeout=None,
        max_retries=2,
        seed=42,
        verbose=False)

    def _setup_email(self):
        self.SMTP_SERVER = "smtp.gmail.com"
        self.SMTP_PORT = 587
        self.EMAIL_ADDRESS = "" # the sender email
        self.APP_PASSWORD = "" #google app password



    def _setup_milvus(self):
        self.milvus_client = MilvusClient("milvus_demo.db")

    # === OCR Extraction ===
    def extract_text_from_image(self, image_path):
        return self.text_extractor.extract_text_paddleocr(image_path)

    # === Document Analysis (Classification + Summarization) ===
    def analyze_document(self, text):
        classification_prompt = PromptTemplate(
            input_variables=["text"],
            template="""
                  classify the provided document into **one of the predefined categories only**. 

                  Strict Instructions:
                  - Choose ONLY from the following categories: [email, invoice, report, legal, resume, article, non-sense, other]
                  - If the text is meaningless, empty, or random characters, classify it as **non-sense**
                  - If you can not determine exactly the category, classify it as **other**
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

        return {
            "document_category": category,
            "summary": summary
        }

    # === Email Notification ===
    def send_email(self, receiver_email, subject, body):
        msg = MIMEMultipart()
        msg["From"] = self.EMAIL_ADDRESS
        msg["To"] = receiver_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            server = smtplib.SMTP(self.SMTP_SERVER, self.SMTP_PORT)
            server.starttls()
            server.login(self.EMAIL_ADDRESS, self.APP_PASSWORD)
            server.sendmail(self.EMAIL_ADDRESS, receiver_email, msg.as_string())
            server.quit()
            return "Email sent successfully!"
        except Exception as e:
            return f"Error: {e}"

    def notify_user(self, email, document_name, category):
        msg = f"Document: {document_name} has been categorized as {category}."
        print(f"📩 Email Sent: {msg}")
        return self.send_email(email, "Document Categorized", msg)

    # === Metadata Helper ===
    def extract_metadata(self, path):
        return os.path.basename(path), os.path.splitext(path)[1]

    # === Full Document Processing Pipeline ===
    def process_and_store(self, file_path):
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
           print("⚠️  This document was categorized as 'non-sense' and will not be stored.")
           print("Please provide a valid document with meaningful content.")
           return  # Exit early
        
        if category.lower() == "other":
           print("⚠️  This document was classified as 'other'. Please enter the correct category manually.")
           category = input("Enter the correct category  ").strip().lower()
    
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
        print(f"✅ The Document Has Been Saved : {res}")

    # === Smart Search ===
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
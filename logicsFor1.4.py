import os
import torch
import uuid
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

from langchain import LLMChain, PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from pymilvus import MilvusClient
import google.generativeai as genai

class DocumentIntelligencePipeline:
    def _init_(self):
        # === Setup APIs and Models ===
        self._setup_gemini_api()
        self._setup_email()
        self._setup_ocr()
        self._setup_milvus()
        self.col_name = "documents_collection"

    def _setup_gemini_api(self):
        os.environ["GOOGLE_API_KEY"] = ''
        genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
        self.llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0, max_tokens=500, timeout=None,
        max_retries=2,
        seed=42,
        verbose=False)

    def _setup_email(self):
        self.SMTP_SERVER = "smtp.gmail.com"
        self.SMTP_PORT = 587
        self.EMAIL_ADDRESS = ""
        self.APP_PASSWORD = ""

    def _setup_ocr(self):
        self.ocr_model = Qwen2VLForConditionalGeneration.from_pretrained(
            "prithivMLmods/Qwen2-VL-OCR-2B-Instruct", torch_dtype="auto", device_map="auto"
        )
        self.ocr_processor = AutoProcessor.from_pretrained(
            "prithivMLmods/Qwen2-VL-OCR-2B-Instruct",
            size={"shortest_edge": 56 * 56, "longest_edge": 28 * 28 * 1280}
        )

    def _setup_milvus(self):
        self.milvus_client = MilvusClient("milvus_demo.db")

    # === OCR Extraction ===
    def extract_text_from_image(self, image_path):
        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "image": image_path},
                {"type": "text", "text": "Extract the text from the image."}
            ]
        }]
        prompt = self.ocr_processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.ocr_processor(
            text=[prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt"
        )
        generated_ids = self.ocr_model.generate(**inputs, max_new_tokens=128)
        trimmed = [out[len(in_):] for in_, out in zip(inputs.input_ids, generated_ids)]
        decoded = self.ocr_processor.batch_decode(trimmed, skip_special_tokens=True)
        return " ".join(decoded).replace("<|im_end|>", "")

    # === Document Analysis (Classification + Summarization) ===
    def analyze_document(self, text):
        classification_prompt = PromptTemplate(
            input_variables=["text"],
            template="""You are an expert in Text Classification. You excel at breaking down complex documents into categories.
                    classify the provided document and determine its category.
                    Your classification should assign category labels to make it clear for the reader to determine the kind of document.
                    Classify the document in one word.

                    example:
                    Dear Hiring Manager,

                    I am excited to apply for the AI Intern position . With about one year of experience in NLP, ML, and Deep Learning, I have developed and deployed models for machine translation, sentiment analysis, and named entity recognition using cutting-edge frameworks like PyTorch and keras. My strong Python and scikit-learn skills, make me a strong fit for your team.

                    I welcome the opportunity to discuss how my skills align with your goals.

                    Best regards,
                    Ali
                    document category: E-mail

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
        print(f"✅ Saved to Milvus: {res}")

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

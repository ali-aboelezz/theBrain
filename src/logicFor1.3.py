import os
import requests
import json
import pandas as pd
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional, Any
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field, validator


class Task(BaseModel):
    """Task model for parsing AI output"""
    task_name: str = Field(description="The name of the task")
    due_date: Optional[str] = Field(None, description="The due date of the task in YYYY-MM-DD format")
    priority: str = Field("Medium", description="The priority of the task: High, Medium, or Low")
    assigned_to: List[str] = Field(default_factory=list, description="List of people assigned to the task")


class TaskList(BaseModel):
    """List of tasks for parsing AI output"""
    tasks: List[Task] = Field(description="List of extracted tasks")


class SecretaryAgent:
    """
    Secretary Agent class that handles task management workflow:
    1. Task extraction from text
    2. Handling missing information
    3. Integration with Trello API to assign tasks
    4. Email notifications to assigned members
    """
    
    def __init__(self):
        # Mistral AI settings
        self.mistral_api_key = "MISTERAL API KEY"
        self.mistral_api_url = "https://api.mistral.ai/v1/chat/completions"
        self.mistral_model = "mistral-large-latest"
        
        # Trello API settings
        self.trello_api_key = "TRELLO API KEY"
        self.trello_token = "TRELLO TOKEN"
        self.trello_username = "USERNAME"
        self.trello_base_params = {"key": self.trello_api_key, "token": self.trello_token}
        
        # Board and list settings
        self.board_id = None
        self.todo_list_id = None
        
        # Email settings
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.email_address = "Elmadany11149@gmail.com"
        self.email_password = "email APP password"
        
        # Setup LangChain Pydantic parser
        self.parser = PydanticOutputParser(pydantic_object=TaskList)
    
    def extract_tasks_from_text(self, text: str) -> List[Dict]:
        """Extract tasks from text using Mistral AI with LangChain parser"""
        format_instructions = self.parser.get_format_instructions()
        
        prompt = (
            "Extract tasks from the given text and return them in JSON format.\n"
            f"{format_instructions}\n"
            "Only return valid JSON without any additional text. If due_date isn't specified, return null for that field.\n"
            "If assigned members aren't explicitly mentioned, leave the assigned_to array empty.\n"
            "Extract all relevant task information based on the context."
        )
        
        headers = {
            "Authorization": f"Bearer {self.mistral_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.mistral_model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text}
            ],
            "temperature": 0.3,
            "max_tokens": 512
        }
        
        try:
            response = requests.post(self.mistral_api_url, headers=headers, json=payload)
            
            if response.status_code != 200:
                print(f"Error: {response.status_code}, {response.text}")
                return []
            
            response_data = response.json()
            raw_json_text = response_data["choices"][0]["message"]["content"]
            
            # Use LangChain parser to parse the JSON response
            try:
                task_list = self.parser.parse(raw_json_text)
                tasks_data = task_list.tasks
            except Exception as parse_error:
                print(f"Error parsing JSON response: {parse_error}")
                print(f"Raw response: {raw_json_text}")
                
                # Fallback: Try to extract JSON directly if LangChain parser fails
                try:
                    # Find JSON content by identifying opening and closing braces
                    json_content = raw_json_text[raw_json_text.find("{"):raw_json_text.rfind("}")+1]
                    parsed_json = json.loads(json_content)
                    task_list = TaskList(**parsed_json)
                    tasks_data = task_list.tasks
                except Exception as fallback_error:
                    print(f"Fallback parsing also failed: {fallback_error}")
                    return []
            
            # Process and format the tasks
            formatted_tasks = []
            for task in tasks_data:
                # Convert date to proper format
                due_date = None
                if task.due_date:
                    try:
                        due_date = datetime.strptime(task.due_date, "%Y-%m-%d")
                    except ValueError:
                        due_date = None
                
                formatted_task = {
                    "name": task.task_name,
                    "due_date": due_date,
                    "priority": task.priority,
                    "assigned_to_names": task.assigned_to,  # Store the names of assigned members
                    "assigned_members": [],  # Will store Trello member IDs after matching
                    "assigned_member_emails": [],  # Store emails for notification
                    "trello_card_id": None,
                    "trello_card_url": None
                }
                
                formatted_tasks.append(formatted_task)
            
            return formatted_tasks
        
        except Exception as e:
            print(f"Error extracting tasks: {e}")
            return []
    
    def prompt_for_missing_info(self, tasks: List[Dict], board_members: List[Dict]) -> List[Dict]:
        """Prompt the user for missing task information"""
        updated_tasks = []
        
        print("\n--- Collecting missing task information ---")
        
        for i, task in enumerate(tasks):
            print(f"\nTask {i+1}: {task['name']}")
            
            # Prompt for due date if not specified
            if not task["due_date"]:
                while True:
                    date_input = input("Due date not specified. Please enter a due date (YYYY-MM-DD): ")
                    try:
                        task["due_date"] = datetime.strptime(date_input, "%Y-%m-%d")
                        break
                    except ValueError:
                        print("Invalid date format. Please use YYYY-MM-DD format.")
            
            # Prompt for assigned members
            print("\nAvailable board members:")
            for j, member in enumerate(board_members):
                print(f"  {j+1}. {member.get('fullName', 'Unknown')}")
            
            while True:
                members_input = input("\nEnter member numbers to assign (comma-separated): ")
                try:
                    member_indices = [int(idx.strip()) - 1 for idx in members_input.split(",")]
                    if all(0 <= idx < len(board_members) for idx in member_indices):
                        # Store both names and IDs
                        task["assigned_to_names"] = [board_members[idx].get("fullName") for idx in member_indices]
                        task["assigned_members"] = [board_members[idx].get("id") for idx in member_indices]
                        break
                    else:
                        print("Invalid member number(s). Please try again.")
                except ValueError:
                    print("Please enter valid numbers separated by commas.")
            
            # Prompt for email addresses for each assigned member
            task["assigned_member_emails"] = []
            for j, member_name in enumerate(task["assigned_to_names"]):
                email = input(f"Enter email address for {member_name}: ")
                task["assigned_member_emails"].append(email)
            
            updated_tasks.append(task)
        
        return updated_tasks
    
    def get_trello_boards(self) -> List[Dict]:
        """Get all Trello boards for the user"""
        url = f"https://api.trello.com/1/members/{self.trello_username}/boards"
        
        try:
            response = requests.get(url, params=self.trello_base_params)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error fetching boards: {response.status_code}, {response.text}")
                return []
        
        except Exception as e:
            print(f"Error getting boards: {e}")
            return []
    
    def get_trello_lists(self, board_id: str) -> List[Dict]:
        """Get all lists in a Trello board"""
        url = f"https://api.trello.com/1/boards/{board_id}/lists"
        
        try:
            response = requests.get(url, params=self.trello_base_params)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error fetching lists: {response.status_code}, {response.text}")
                return []
        
        except Exception as e:
            print(f"Error getting lists: {e}")
            return []
    
    def get_trello_board_members(self, board_id: str) -> List[Dict]:
        """Get all members of a Trello board"""
        url = f"https://api.trello.com/1/boards/{board_id}/members"
        
        try:
            response = requests.get(url, params=self.trello_base_params)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error fetching members: {response.status_code}, {response.text}")
                return []
        
        except Exception as e:
            print(f"Error getting board members: {e}")
            return []
    
    def get_trello_member_details(self, member_id: str) -> Dict:
        """Get details for a specific Trello member"""
        url = f"https://api.trello.com/1/members/{member_id}"
        
        try:
            response = requests.get(url, params=self.trello_base_params)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error fetching member details: {response.status_code}, {response.text}")
                return {}
        
        except Exception as e:
            print(f"Error getting member details: {e}")
            return {}
    
    def create_trello_card(self, list_id: str, task: Dict) -> Dict:
        """Create a card in a Trello list for a task"""
        url = "https://api.trello.com/1/cards"
        
        params = {
            **self.trello_base_params,
            "idList": list_id,
            "name": task["name"],
            "desc": f"Priority: {task['priority']}"
        }
        
        if task["due_date"]:
            params["due"] = task["due_date"].strftime("%Y-%m-%dT%H:%M:%S.000Z")
        
        try:
            response = requests.post(url, params=params)
            
            if response.status_code == 200:
                card = response.json()
                task["trello_card_id"] = card["id"]
                task["trello_card_url"] = card["shortUrl"]
                return card
            else:
                print(f"Error creating card: {response.status_code}, {response.text}")
                return {}
        
        except Exception as e:
            print(f"Error creating Trello card: {e}")
            return {}
    
    def assign_member_to_card(self, card_id: str, member_id: str) -> bool:
        """Assign a member to a Trello card"""
        url = f"https://api.trello.com/1/cards/{card_id}/idMembers"
        
        params = {
            **self.trello_base_params,
            "value": member_id
        }
        
        try:
            response = requests.post(url, params=params)
            
            if response.status_code == 200:
                return True
            else:
                print(f"Error assigning member: {response.status_code}, {response.text}")
                return False
        
        except Exception as e:
            print(f"Error assigning member to card: {e}")
            return False
    
    def send_email_notification(self, to_email: str, subject: str, body: str) -> bool:
        """Send an email notification"""
        try:
            msg = MIMEMultipart()
            msg["From"] = self.email_address
            msg["To"] = to_email
            msg["Subject"] = subject
            
            msg.attach(MIMEText(body, "plain"))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_address, self.email_password)
                server.send_message(msg)
            
            print(f"Successfully sent email to {to_email}")
            return True
        
        except Exception as e:
            print(f"Error sending email: {e}")
            return False
    
    def notify_task_assignment(self, task: Dict, member_email: str, member_name: str) -> None:
        """Notify a member about a new task assignment"""
        subject = f"New Task Assigned: {task['name']}"
        
        body = (
            f"Dear {member_name},\n\n"
            f"You have been assigned a new task:\n"
            f"Task: {task['name']}\n"
            f"Priority: {task['priority']}\n"
            f"Due Date: {task['due_date'].strftime('%Y-%m-%d') if task['due_date'] else 'Not specified'}\n"
            f"Trello Link: {task['trello_card_url']}\n\n"
            f"Please check Trello for more details.\n\n"
            f"Best regards,\nYour Secretary Agent"
        )
        
        self.send_email_notification(member_email, subject, body)
    
    def select_board(self) -> str:
        """Select a Trello board to use for task creation"""
        boards = self.get_trello_boards()
        
        if not boards:
            raise Exception("No Trello boards found")
        
        print("\nAvailable Trello boards:")
        for i, board in enumerate(boards):
            print(f"{i+1}. {board['name']}")
        
        while True:
            choice = input("\nSelect a board (enter number): ")
            try:
                board_index = int(choice) - 1
                if 0 <= board_index < len(boards):
                    selected_board = boards[board_index]
                    print(f"Selected board: {selected_board['name']}")
                    return selected_board["id"]
                else:
                    print("Invalid board number. Please try again.")
            except ValueError:
                print("Please enter a valid number.")
    
    def find_todo_list(self, board_id: str) -> str:
        """Find the 'To Do' list in the specified board"""
        lists = self.get_trello_lists(board_id)
        
        if not lists:
            raise Exception(f"No lists found in the selected board")
        
        # Try to find a list with 'To Do' in the name
        todo_list = None
        for lst in lists:
            if "to do" in lst["name"].lower():
                todo_list = lst
                break
        
        # If no 'To Do' list found, use the first list
        if not todo_list:
            todo_list = lists[0]
            print(f"No 'To Do' list found. Using the first list: {todo_list['name']}")
        else:
            print(f"Found 'To Do' list: {todo_list['name']}")
        
        return todo_list["id"]
    
    def setup_board_and_list(self) -> bool:
        """Setup the board and list for task creation"""
        try:
            print("\n=== Trello Board Selection ===")
            print("You must select a Trello board to continue.")
            self.board_id = self.select_board()
            self.todo_list_id = self.find_todo_list(self.board_id)
            return True
        except Exception as e:
            print(f"Error setting up board and list: {e}")
            return False
    
    def process_text_and_create_tasks(self, text: str) -> List[Dict]:
        """Process text to extract and create tasks in Trello"""
        print("Starting task extraction...")
        tasks = self.extract_tasks_from_text(text)
        
        if not tasks:
            print("No tasks could be extracted from the text")
            return []
        
        print(f"Extracted {len(tasks)} tasks from the text")
        
        try:
            # Get board members for assignment
            board_members = self.get_trello_board_members(self.board_id)
            
            # Check for missing information and prompt user
            tasks = self.prompt_for_missing_info(tasks, board_members)
            
            created_tasks = []
            
            # Create cards in Trello and notify members
            for task in tasks:
                print(f"Creating Trello card for task: {task['name']}")
                card = self.create_trello_card(self.todo_list_id, task)
                
                if not card:
                    print(f"Failed to create card for task: {task['name']}")
                    continue
                
                print(f"Successfully created card: {card['shortUrl']}")
                created_tasks.append(task)
                
                # Assign members to the card
                for i, member_id in enumerate(task["assigned_members"]):
                    if self.assign_member_to_card(card["id"], member_id):
                        print(f"Successfully assigned {task['assigned_to_names'][i]} to the card")
                        
                        # Send email notification using the provided email
                        if i < len(task["assigned_member_emails"]):
                            self.notify_task_assignment(
                                task,
                                task["assigned_member_emails"][i],
                                task["assigned_to_names"][i]
                            )
            
            return created_tasks
        
        except Exception as e:
            print(f"Error processing text and creating tasks: {e}")
            return []
    
    def run(self):
        """Main method to run the secretary agent"""
        print("\n===== Secretary Agent =====")
        print("Your intelligent task manager")
        print("===========================")
        
        # Always force the user to select a board at startup
        if not self.setup_board_and_list():
            print("Failed to set up Trello board. Exiting.")
            return
        
        while True:
            print("\nWhat would you like to do?")
            print("1. create new task")
            print("2. Change Trello board")
            print("3. Exit")
            
            choice = input("\nEnter your choice (1-3): ")
            
            if choice == "1":
                text = input("\nEnter the text to extract tasks from:\n")
                tasks = self.process_text_and_create_tasks(text)
                
                if tasks:
                    print("\nSuccessfully created the following tasks:")
                    for i, task in enumerate(tasks, 1):
                        due_date_str = task["due_date"].strftime("%Y-%m-%d") if task["due_date"] else "Not specified"
                        assigned_to = ", ".join(task["assigned_to_names"]) if task["assigned_to_names"] else "No one"
                        print(f"{i}. {task['name']} - Due: {due_date_str} - Priority: {task['priority']} - Assigned to: {assigned_to}")
                else:
                    print("\nNo tasks were created.")
            
            elif choice == "2":
                self.setup_board_and_list()
            
            elif choice == "3":
                print("\nThank you for using Secretary Agent. Goodbye!")
                break
            
            else:
                print("\nInvalid choice. Please try again.")


if __name__ == "__main__":
    secretary = SecretaryAgent()
    secretary.run()
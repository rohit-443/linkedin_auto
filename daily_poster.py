import os
import json
import random
import requests
from datetime import datetime
import google.generativeai as genai
from html2image import Html2Image
from PIL import Image, ImageChops
import smtplib
from email.message import EmailMessage
import re

# PATHS
DIR_PATH = os.path.dirname(os.path.abspath(__file__))
SUBJECT_PATH = os.path.join(DIR_PATH, "subject.json")
STATE_PATH = os.path.join(DIR_PATH, "state.json")
HISTORY_PATH = os.path.join(DIR_PATH, "history.jsonl")
TOKEN_PATH = os.path.join(DIR_PATH, "linked_in_token.json")

def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def append_history(entry):
    with open(HISTORY_PATH, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + "\n")

class DailyInterviewPoster:
    def __init__(self):
        # Load configs
        self.config = load_json(TOKEN_PATH)
        self.subject = load_json(SUBJECT_PATH)
        self.state = load_json(STATE_PATH)
        
        self.gemini_api_key = self.config.get("gemini_api_key")
        self.dropbox_refresh_token = self.config.get("DROPBOX_REFRESH_TOKEN")
        self.dropbox_client_id = self.config.get("DROPBOX_CLIENT_ID")
        self.dropbox_client_secret = self.config.get("DROPBOX_CLIENT_SECRET")
        self.gmail_id = self.config.get("INTERVIEW_GMAIL_ID")
        self.gmail_password = self.config.get("GOOGLE_APP_PASSWORD")
        
        # Configure Gemini
        genai.configure(api_key=self.gemini_api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        self.hti = Html2Image()
        self.hti.browser.flags = ['--no-sandbox', '--disable-gpu', '--hide-scrollbars']

    def select_topic(self):
        if not self.state["pending_topics"]:
            raise Exception("No more pending topics left!")
        
        current_topic = self.state["pending_topics"][0] # Take the first one
        combined_topic = None
        
        if self.state["covered_topics"]:
            # Pick a random previous topic to combine ideas
            combined_topic = random.choice(self.state["covered_topics"])
            
        return current_topic, combined_topic

    def generate_content(self, current_topic, combined_topic):
        print(f"Generating questions and post description for topic: {current_topic}")
        recent = self.state.get("recent_questions", [])
        recent_str = "\\n- ".join(recent[-30:]) if recent else "None"
        
        prompt = f"""
        You are an expert technical interviewer and LinkedIn content creator for {self.subject['tool_name']}.
        Target Audience: {self.subject['audience']}
        Skill Description: {self.subject['skill_description']}
        
        Today's Primary Topic: {current_topic}
        """
        
        if combined_topic:
            prompt += f"\\nOptionally, you can blend in concepts from this previously covered topic: {combined_topic}"
            
        prompt += f"""
        
        Avoid generating ANY questions that exactly match these recently asked questions:
        - {recent_str}
        
        Task: 
        1. Write an engaging LinkedIn post description (around 3-4 sentences) introducing the topic and encouraging followers to swipe through the 7 interview questions. Include relevant hashtags like #interviewprep #dataengineering.
        2. Generate EXACTLY 7 interview questions related to the Primary Topic. For each question, provide a detailed, comprehensive, and practical solution. The solution can be as long as necessary to fully explain the concept.
           - Limit the solution to a maximum of 5 bullet points if it is long.
           - Provide short, clear programming examples heavily formatting them appropriately.
           - Emphasize formatting cleanly.
        
        Return the result STRICTLY as a JSON object matching this exact schema:
        {{
          "post_description": "...",
          "questions": [
            {{"question": "...", "solution": "..."}},
            ...
          ]
        }}
        
        IMPORTANT: Your output will be parsed natively via Python's json.loads(). 
        Ensure all internal string contents, especially code blocks or newlines, are correctly escaped (e.g., use \\n for newlines, \\t for tabs, and double escape backslashes like \\\\d or \\\\ if writing code).
        """
        
        # Enforce JSON output using generation config
        response = self.model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.7
            )
        )
        
        try:
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text.replace("```json", "", 1)
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()
            
            data = json.loads(raw_text, strict=False)
            if len(data["questions"]) > 7:
                data["questions"] = data["questions"][:7]
            return data
        except json.JSONDecodeError as e:
            print("Failed to decode JSON from Gemini. Raw response:")
            print(response.text)
            raise

    def generate_image(self, index, topic, question_obj):
        q_text = question_obj['question'].replace('"', '&quot;').replace("'", '&apos;')
        s_text = question_obj['solution'].replace('"', '&quot;').replace("'", '&apos;')
        
        # Remove markdown bold heavily
        q_text = q_text.replace('**', '')
        s_text = s_text.replace('**', '')
        
        # Handle markdown blocks and parse to HTML pre tags
        s_text = re.sub(
            r'```[a-zA-Z]*\n?(.*?)```', 
            r'<pre style="background-color:#E8E8E8; padding:20px; border-radius:8px; font-family: monospace; font-size: 28px; white-space: pre-wrap;"><code>\1</code></pre>', 
            s_text, 
            flags=re.DOTALL
        )
        
        # Finally, safely replace newlines with BR
        q_text = q_text.replace('\n', '<br>')
        s_text = s_text.replace('\n', '<br>')
        
        # HTML Template matching user specification
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <style>
            body {{
                margin: 0;
                padding: 0;
                width: 1500px;
                background-color: #FFFFFF;
                font-family: 'Segoe UI', Arial, sans-serif;
                position: relative;
            }}
            /* Yellow sectored circle (top-left) */
            .top-left-circle {{
                position: absolute;
                top: 0;
                left: 0;
                width: 250px;
                height: 250px;
                background-color: #FFD700;
                border-bottom-right-radius: 250px;
            }}
            /* Red sectored circle (top-right) */
            .top-right-circle {{
                position: absolute;
                top: 0;
                right: 0;
                width: 250px;
                height: 250px;
                background-color: #FF4500;
                border-bottom-left-radius: 250px;
            }}
            /* Light purple horizontal strip */
            .ribbon {{
                width: 100%;
                background-color: #E6E6FA;
                padding: 30px 250px;
                box-sizing: border-box;
                text-align: center;
                margin-top: 100px;
            }}
            .ribbon-text {{
                font-size: 36px;
                font-weight: bold;
                color: #333333;
                text-transform: uppercase;
                letter-spacing: 2px;
            }}
            .content {{
                padding: 80px 100px 20px 100px;
                color: #000000;
            }}
            .question-box {{
                font-size: 42px;
                font-weight: 700;
                line-height: 1.4;
                margin-bottom: 50px;
            }}
            .solution-box {{
                font-size: 36px;
                font-weight: 400;
                line-height: 1.5;
                color: #222222;
                background-color: #F8F9FA;
                padding: 40px;
                border-left: 8px solid #FFD700;
                border-radius: 8px;
            }}
            .footer {{
                text-align: right;
                font-size: 24px;
                color: #777777;
                font-style: italic;
                padding: 0px 60px 40px 0;
            }}
        </style>
        </head>
        <body>
            <div class="top-left-circle"></div>
            <div class="top-right-circle"></div>
            <div class="ribbon">
                <div class="ribbon-text">{topic}</div>
            </div>
            <div class="content">
                <div class="question-box">Q: {q_text}</div>
                <div class="solution-box"><strong>Solution:</strong><br>{s_text}</div>
            </div>
            <div class="footer">#{index}/7 Daily {self.subject['tool_name']} Prep</div>
        </body>
        </html>
        """
        
        output_file = f"question_{index}.png"
        self.hti.screenshot(html_str=html_content, save_as=output_file, size=(1500, 6000))
        
        with Image.open(output_file) as img:
            rgb_img = img.convert('RGB')
            bg = Image.new(rgb_img.mode, rgb_img.size, (255, 255, 255))
            diff = ImageChops.difference(rgb_img, bg)
            diff = ImageChops.add(diff, diff, 2.0, -100)
            bbox = diff.getbbox()
            if bbox:
                rgb_img = rgb_img.crop((0, 0, rgb_img.width, bbox[3] + 40))
            rgb_img.save(output_file, 'PNG')
            
        return output_file

    def get_dropbox_access_token(self):
        url = "https://api.dropbox.com/oauth2/token"
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.dropbox_refresh_token,
            "client_id": self.dropbox_client_id,
            "client_secret": self.dropbox_client_secret
        }
        res = requests.post(url, data=data)
        res.raise_for_status()
        return res.json()["access_token"]

    def upload_to_dropbox(self, file_path, target_path):
        access_token = self.get_dropbox_access_token()
        url = "https://content.dropboxapi.com/2/files/upload"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Dropbox-API-Arg": json.dumps({
                "path": target_path,
                "mode": "add",
                "autorename": True,
                "mute": False,
                "strict_conflict": False
            }),
            "Content-Type": "application/octet-stream"
        }
        with open(file_path, "rb") as f:
            data = f.read()
        res = requests.post(url, headers=headers, data=data)
        res.raise_for_status()
        return res.json()

    def get_dropbox_shared_link(self, path):
        access_token = self.get_dropbox_access_token()
        url = "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        data = {
            "path": path,
            "settings": {
                "requested_visibility": "public"
            }
        }
        res = requests.post(url, headers=headers, json=data)
        if res.status_code == 200:
            return res.json().get("url")
        elif res.status_code == 409 and "shared_link_already_exists" in res.text:
            url_list = "https://api.dropboxapi.com/2/sharing/list_shared_links"
            data_list = {"path": path}
            res_list = requests.post(url_list, headers=headers, json=data_list)
            if res_list.status_code == 200:
                links = res_list.json().get("links", [])
                if links:
                    return links[0].get("url")
        return f"Could not generate link for {path}"

    def send_success_email(self, topic, shared_link):
        if not self.gmail_id or not self.gmail_password:
            print("Email credentials missing. Skipping email alert.")
            return

        subject = f"✅ Success: Daily Interview Poster - {topic}"
        body = f"""
The daily interview questions have been generated and uploaded to Dropbox successfully.

Topic: {topic}
Dropbox Folder Link: {shared_link}
        """

        msg = EmailMessage()
        msg.set_content(body)
        msg['Subject'] = subject
        msg['From'] = self.gmail_id
        msg['To'] = self.gmail_id  # Sending alert to self

        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(self.gmail_id, self.gmail_password)
                server.send_message(msg)
            print("Successfully sent success email alert.")
        except Exception as e:
            print(f"Failed to send email alert: {e}")

    def run(self):
        # 1. State
        current_topic, combined_topic = self.select_topic()
        
        # 2. Extract Questions and Description
        generated_data = self.generate_content(current_topic, combined_topic)
        post_description = generated_data["post_description"]
        questions = generated_data["questions"]
        
        # 3. Images + Upload
        date_folder = datetime.now().strftime('%Y%m%d_%H%M%S')
        dropbox_paths = []
        for i, q in enumerate(questions):
            print(f"Generating image {i+1}/7...")
            img_path = self.generate_image(i+1, current_topic, q)
            print(f"Uploading image {i+1}/7 to Dropbox...")
            target_path = f"/interview_questions/databricks_pyspark/{date_folder}/question_{i+1}.png"
            self.upload_to_dropbox(img_path, target_path)
            dropbox_paths.append(target_path)
        
        print("Images securely stored in Dropbox.")
        
        # 5. Update State
        self.state["pending_topics"].pop(0)
        self.state["covered_topics"].append(current_topic)
        
        # Track asked questions to prevent duplicates
        for q in questions:
            self.state["recent_questions"].append(q["question"])
            
        # Keep window small
        if len(self.state["recent_questions"]) > 50:
            self.state["recent_questions"] = self.state["recent_questions"][-50:]
            
        save_json(self.state, STATE_PATH)
        
        # 6. Append History
        history_entry = {
            "date": datetime.now().isoformat(),
            "topic": current_topic,
            "combined_topic": combined_topic,
            "post_description": post_description,
            "questions_posted": questions,
            "dropbox_folder": date_folder
        }
        append_history(history_entry)
        
        # 6.5 Append Proof of Concept Plain Text Log
        poc_path = os.path.join(DIR_PATH, "daily_responses.txt")
        with open(poc_path, "a", encoding="utf-8") as f:
            f.write(f"--- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            f.write(f"Topic: {current_topic}\n")
            clean_desc = post_description.replace('**', '')
            f.write(f"Description: {clean_desc}\n\n")
            for i, q in enumerate(questions):
                clean_q = q["question"].replace('**', '')
                clean_s = q["solution"].replace('**', '')
                f.write(f"Q{i+1}: {clean_q}\n")
                f.write(f"Solution: {clean_s}\n\n")
            f.write("\n")
        
        # 7. Send Email Alert
        folder_path = f"/interview_questions/databricks_pyspark/{date_folder}"
        shared_link = self.get_dropbox_shared_link(folder_path)
        self.send_success_email(current_topic, shared_link)
        
        print("✅ Daily run complete!")

if __name__ == "__main__":
    poster = DailyInterviewPoster()
    poster.run()

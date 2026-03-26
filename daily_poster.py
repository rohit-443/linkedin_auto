import os
import json
import random
import requests
from datetime import datetime
import google.generativeai as genai
from html2image import Html2Image
from PIL import Image

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
        
        self.access_token = self.config["access_token"]
        self.gemini_api_key = self.config["gemini_api_key"]
        
        # Configure Gemini
        genai.configure(api_key=self.gemini_api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Configure LinkedIn
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'X-Restli-Protocol-Version': '2.0.0',
            'LinkedIn-Version': '202401'
        }
        self.user_urn = self.get_user_urn()
        self.hti = Html2Image()
        self.hti.browser.flags = ['--no-sandbox', '--disable-gpu', '--hide-scrollbars']

    def get_user_urn(self):
        url = "https://api.linkedin.com/v2/userinfo"
        res = requests.get(url, headers={'Authorization': f'Bearer {self.access_token}'})
        res.raise_for_status()
        return f"urn:li:person:{res.json()['sub']}"

    def select_topic(self):
        if not self.state["pending_topics"]:
            raise Exception("No more pending topics left!")
        
        current_topic = self.state["pending_topics"][0] # Take the first one
        combined_topic = None
        
        if self.state["covered_topics"]:
            # Pick a random previous topic to combine ideas
            combined_topic = random.choice(self.state["covered_topics"])
            
        return current_topic, combined_topic

    def generate_questions(self, current_topic, combined_topic):
        print(f"Generating questions for topic: {current_topic}")
        recent = self.state.get("recent_questions", [])
        recent_str = "\\n- ".join(recent[-30:]) if recent else "None"
        
        prompt = f"""
        You are an expert technical interviewer for {self.subject['tool_name']}.
        Target Audience: {self.subject['audience']}
        Skill Description: {self.subject['skill_description']}
        
        Today's Primary Topic: {current_topic}
        """
        
        if combined_topic:
            prompt += f"\\nOptionally, you can blend in concepts from this previously covered topic: {combined_topic}"
            
        prompt += f"""
        
        Avoid generating ANY questions that exactly match these recently asked questions:
        - {recent_str}
        
        Task: Generate EXACTLY 7 interview questions related to the Primary Topic.
        For each question, provide a practical, highly concise solution (maximum 40 words for the solution).
        
        Return the result STRICTLY as a JSON array of objects with 'question' and 'solution' keys:
        [
          {{"question": "...", "solution": "..."}},
          ...
        ]
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
            questions_data = json.loads(response.text)
            if len(questions_data) > 7:
                questions_data = questions_data[:7]
            return questions_data
        except json.JSONDecodeError:
            print("Failed to decode JSON from Gemini. Raw response:")
            print(response.text)
            raise

    def generate_image(self, index, topic, question_obj):
        q_text = question_obj['question']
        s_text = question_obj['solution']
        
        # HTML Template matching user specification
        html_content = f\"\"\"
        <!DOCTYPE html>
        <html>
        <head>
        <style>
            body {{
                margin: 0;
                padding: 0;
                width: 1080px;
                height: 1080px;
                background-color: #FFFFFF;
                font-family: 'Segoe UI', Arial, sans-serif;
                position: relative;
                overflow: hidden;
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
                padding: 80px 100px;
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
                position: absolute;
                bottom: 40px;
                right: 60px;
                font-size: 24px;
                color: #777777;
                font-style: italic;
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
        \"\"\"
        
        output_file = f"question_{index}.png"
        self.hti.screenshot(html_str=html_content, save_as=output_file, size=(1080, 1080))
        
        # Strip Alpha channel
        with Image.open(output_file) as img:
            rgb_img = img.convert('RGB')
            rgb_img.save(output_file, 'PNG')
            
        return output_file

    def register_and_upload(self, file_path):
        url = "https://api.linkedin.com/v2/assets?action=registerUpload"
        payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": self.user_urn,
                "serviceRelationships": [{"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}]
            }
        }
        res = requests.post(url, headers=self.headers, json=payload)
        res.raise_for_status()
        data = res.json()
        upload_url = data['value']['uploadMechanism']['com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest']['uploadUrl']
        asset_urn = data['value']['asset']
        
        # Upload binary
        with open(file_path, 'rb') as f:
            image_data = f.read()
            
        upload_headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'image/png'
        }
        upload_res = requests.post(upload_url, data=image_data, headers=upload_headers)
        upload_res.raise_for_status()
        
        return asset_urn

    def post_to_linkedin(self, topic, asset_urns):
        url = "https://api.linkedin.com/v2/ugcPosts"
        media_items = [{"status": "READY", "media": urn} for urn in asset_urns]
        
        text = f"🚀 Daily {self.subject['tool_name']} Interview Prep! 🚀\\n\\nToday's Topic: {topic}\\n\\nSwipe through the 7 technical questions for your interview preparation. Save this post to refer back to later! 👇\\n\\n#interviewprep #dataengineering #spark #databricks"
        
        payload = {
            "author": self.user_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "IMAGE",
                    "media": media_items
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
        }
        
        res = requests.post(url, headers=self.headers, json=payload)
        res.raise_for_status()
        return res.json()

    def run(self):
        # 1. State
        current_topic, combined_topic = self.select_topic()
        
        # 2. Extract Questions
        questions = self.generate_questions(current_topic, combined_topic)
        
        # 3. Images + Upload
        asset_urns = []
        for i, q in enumerate(questions):
            print(f"Generating image {i+1}/7...")
            img_path = self.generate_image(i+1, current_topic, q)
            print(f"Uploading image {i+1}/7...")
            urn = self.register_and_upload(img_path)
            asset_urns.append(urn)
        
        # 4. Post
        print("Publishing to LinkedIn feed...")
        post_response = self.post_to_linkedin(current_topic, asset_urns)
        
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
            "questions_posted": questions,
            "linkedin_urn": post_response.get("id") # The X-RestLi-Id or URN from response
        }
        append_history(history_entry)
        
        print("✅ Daily run complete!")

if __name__ == "__main__":
    poster = DailyInterviewPoster()
    poster.run()

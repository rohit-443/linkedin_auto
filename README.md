# AI Interview Prep Agent (Databricks & PySpark)

This repository hosts an autonomous AI agent designed to automatically generate, format, and securely archive comprehensive Databricks and PySpark interview questions three times a day. 

## What This Agent is Meant For
Consistent, high-quality interview preparation. Rather than manually thinking of questions or searching the web, this agent:
1. Systematically moves through a structured syllabus (`subject.json`).
2. Leverages advanced LLM generation to create highly detailed, comprehensive flashcards (including code examples).
3. Securely catalogs everything in the cloud (Dropbox).
4. Proactively emails you the results on a strictly automated schedule.

## How We Achieved This (The Architecture)

The system is a fully automated, stateless Python pipeline (`daily_poster.py`) orchestrated by **GitHub Actions**. Here is the step-by-step breakdown of how it works under the hood:

1. **State Management (`state.json` & `history.jsonl`)**: 
   The script first checks its local state to see what topics from the syllabus are pending, what has been covered, and exactly what questions were recently asked. This prevents duplicate generation.
   
2. **AI Content Generation (Google Gemini API)**: 
   The agent utilizes **Gemini 2.5 Flash** to generate exactly 7 practical interview questions for the day's topic. We use strict prompting to enforce detailed solutions (up to 5 bullet points), programming examples, and pure JSON output formatting.
   
3. **Dynamic Image Rendering (`html2image` + `Pillow`)**: 
   The generated text (complete with HTML tags, code blocks `<pre>`, and line breaks `<br>`) is injected into a beautifully stylized CSS template designed to be **1500px wide**. 
   - Chrome Headless renders the HTML.
   - We use Python's `PIL.ImageChops` to accurately calculate the bounding box of the content and automatically crop off any excess white space, ensuring the flashcard perfectly fits any length of text.

4. **Cloud Archiving (Dropbox API)**: 
   The 7 cleanly cropped PNG images are seamlessly uploaded into a newly created timestamped Dropbox folder (e.g., `/interview_questions/databricks_pyspark/20261025_103000/`).
   - The script then queries the Dropbox API again to generate a **publicly accessible Shared Link** for this specific folder.

5. **SMTP Notification (Gmail)**: 
   To alert you of completion, Python's native `smtplib` authenticates with Gmail via an App Password and sends you an email containing the topic name and the direct Dropbox Shared Link to view your new flashcards instantly.

6. **Continuous Deployment (GitHub Actions)**: 
   After finishing, the `.github/workflows/daily_post.yml` workflow immediately commits the newly updated `state.json` and `history.jsonl` back into the `main` branch, ensuring the next run picks up exactly where it left off. This workflow runs entirely unattended **3 times a day**.

## Deployment & Setup Instructions

To deploy this robot on your own branch, you only need to configure GitHub Secrets.

1. Go to your repository on GitHub.
2. Navigate to **Settings > Secrets and variables > Actions**.
3. Add the following 6 secrets:
   - `GEMINI_API_KEY`: API Key from Google AI Studio.
   - `DROPBOX_REFRESH_TOKEN`: Long-lived OAuth2 refresh token for Dropbox authorization.
   - `DROPBOX_CLIENT_ID`: Your Dropbox App Key.
   - `DROPBOX_CLIENT_SECRET`: Your Dropbox App Secret.
   - `INTERVIEW_GMAIL_ID`: The sending/receiving email address.
   - `GOOGLE_APP_PASSWORD`: A 16-character App Password generated from your Google Security settings.

Once these secrets are configured and the repository is pushed to the `main` branch, **GitHub Actions takes full control.** No local execution environments or Jupyter notebooks are required!

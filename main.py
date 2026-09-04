import json
import pymupdf
from ollama import chat


def extract_resume_text(pdf_path: str) -> str:
    document = pymupdf.open(pdf_path)

    text = "\n".join(page.get_text() for page in document)

    document.close()

    return text


def analyze_resume(resume_text: str):

    prompt = f"""
You are a career intelligence system.

Analyze the following resume and extract the candidate's professional profile.

IMPORTANT:
- Only use information explicitly present in the resume.
- Do not invent skills, experience, projects, employers, or qualifications.
- Preserve the candidate's actual experience.
- We will use this information later to determine whether the candidate
  should apply to jobs.
- Return ONLY valid JSON.
- Do NOT use markdown.
- Do NOT wrap the JSON in ```.

Use exactly this JSON structure:

{{
    "name": "",
    "summary": "",

    "skills": {{
        "programming_languages": [],
        "frameworks": [],
        "cloud": [],
        "devops_infrastructure": [],
        "databases": [],
        "data_engineering": [],
        "observability": [],
        "ml_ai": []
    }},

    "experience": [
        {{
            "company": "",
            "role": "",
            "start_date": "",
            "end_date": "",
            "responsibilities": []
        }}
    ],

    "projects": [],

    "certifications": [],

    "education": []
}}

RESUME:
{resume_text}
"""

    response = chat(
        model="gemma3:4b",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    raw_response = response["message"]["content"].strip()

    if raw_response.startswith("```"):
        raw_response = raw_response.replace("```json", "", 1)
        raw_response = raw_response.replace("```", "", 1)
        raw_response = raw_response.strip()

    try:
        profile = json.loads(raw_response)
        return profile

    except json.JSONDecodeError:
        print("ERROR: Gemma did not return valid JSON.")
        print("\nRaw response:\n")
        print(raw_response)
        return None


if __name__ == "__main__":

    resume_path = "resume/Krinal Naghera.pdf"

    resume_text = extract_resume_text(resume_path)

    print("Resume extracted successfully.")
    print(f"Characters extracted: {len(resume_text)}")

    print("\nAnalyzing resume with local AI...\n")

    profile = analyze_resume(resume_text)

    if profile:

        print("Resume analysis successful.")

        output_path = "app/data/candidate_profile.json"

        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(profile, file, indent=4, ensure_ascii=False)

        print(f"Candidate profile saved to: {output_path}")

        print("\nCandidate:")
        print(profile["name"])

        print("\nProgramming Languages:")
        print(", ".join(profile["skills"]["programming_languages"]))

        print("\nCloud:")
        print(", ".join(profile["skills"]["cloud"]))
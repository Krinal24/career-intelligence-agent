import json
import re
from pathlib import Path
from datetime import datetime

from ollama import chat


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PROFILE_PATH = PROJECT_ROOT / "app" / "data" / "candidate_profile.json"
JOBS_PATH = PROJECT_ROOT / "app" / "data" / "jobs.json"
OUTPUT_PATH = PROJECT_ROOT / "app" / "data" / "matched_jobs.json"

OLLAMA_MODEL = "gemma3:4b"

# Number of jobs sent to Gemma after rule-based filtering
AI_EVALUATION_COUNT = 15

# Final score weights
RULE_BASED_WEIGHT = 0.30
AI_WEIGHT = 0.70


# ============================================================
# GENERAL HELPERS
# ============================================================

def normalize(text):
    """
    Normalize text for keyword matching.
    """
    if not text:
        return ""

    text = str(text).lower()

    replacements = {
        "kubernetes": "k8s",
        "continuous integration": "cicd",
        "continuous deployment": "cicd",
        "ci/cd": "cicd",
        "machine-learning": "machine learning",
        "machine learning": "machine learning",
        "artificial intelligence": "ai",
        "generative-ai": "generative ai",
        "large language model": "llm",
        "large language models": "llm",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return re.sub(r"\s+", " ", text)


def contains_skill(text, skill):
    """
    More reliable skill matching.

    Short skills such as 'ai', 'r', 'go', etc. are matched
    using word boundaries to avoid accidental substring matches.
    """
    text = normalize(text)
    skill = normalize(skill)

    if not skill:
        return False

    pattern = r"\b" + re.escape(skill) + r"\b"

    return bool(re.search(pattern, text))


def flatten_candidate_skills(profile):
    """
    Flatten all categorized skills into one list.
    """
    skills = []

    for category, values in profile.get("skills", {}).items():

        if not isinstance(values, list):
            continue

        for value in values:

            if isinstance(value, str):
                skills.append(value)

    return list(dict.fromkeys(skills))


def candidate_full_text(profile):
    """
    Create a text representation of the candidate profile.
    """
    parts = []

    parts.append(profile.get("name", ""))
    parts.append(profile.get("summary", ""))

    # Skills
    for category, skills in profile.get("skills", {}).items():
        if isinstance(skills, list):
            parts.append(" ".join(skills))

    # Experience
    for experience in profile.get("experience", []):

        if not isinstance(experience, dict):
            continue

        parts.append(experience.get("company", ""))
        parts.append(experience.get("role", ""))

        responsibilities = experience.get("responsibilities", [])

        if isinstance(responsibilities, list):
            parts.append(" ".join(responsibilities))

    # Projects
    for project in profile.get("projects", []):

        if isinstance(project, str):
            parts.append(project)

        elif isinstance(project, dict):
            parts.append(project.get("name", ""))
            parts.append(project.get("description", ""))

    # Certifications
    certifications = profile.get("certifications", [])

    if isinstance(certifications, list):
        parts.append(" ".join(certifications))

    return normalize(" ".join(parts))


# ============================================================
# EXPERIENCE
# ============================================================

def calculate_candidate_experience(profile):
    """
    Estimate professional experience from resume dates.

    We deliberately exclude current education from this calculation.
    """
    dates = []

    for experience in profile.get("experience", []):

        if not isinstance(experience, dict):
            continue

        start = experience.get("start_date", "")

        if not start:
            continue

        match = re.search(r"(\d{4})", str(start))

        if match:
            dates.append(int(match.group(1)))

    if not dates:
        return 1.5

    earliest_year = min(dates)

    current_date = datetime.now()

    experience_years = current_date.year - earliest_year

    return max(1.0, float(experience_years))


def extract_required_experience(job_text):
    """
    Extract experience requirements from a job description.

    We intentionally look for explicit phrases rather than taking
    every 'X years' occurrence in the description.
    """

    text = normalize(job_text)

    patterns = [
        r"(\d+(?:\.\d+)?)\+?\s*years?\s+of\s+(?:relevant\s+)?experience",
        r"minimum\s+of\s+(\d+(?:\.\d+)?)\s*years?",
        r"at\s+least\s+(\d+(?:\.\d+)?)\s*years?",
        r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*years?",
    ]

    values = []

    for pattern in patterns:

        matches = re.findall(pattern, text)

        for match in matches:

            if isinstance(match, tuple):

                for value in match:
                    try:
                        values.append(float(value))
                    except ValueError:
                        pass

            else:

                try:
                    values.append(float(match))
                except ValueError:
                    pass

    if not values:
        return None

    return max(values)


def experience_score(candidate_years, required_years):
    """
    Score experience fit.
    """

    if required_years is None:
        return 80

    if candidate_years >= required_years:
        return 100

    gap = required_years - candidate_years

    if gap <= 0.5:
        return 90

    if gap <= 1:
        return 75

    if gap <= 2:
        return 50

    if gap <= 3:
        return 25

    return 10


# ============================================================
# ROLE MATCHING
# ============================================================

ROLE_GROUPS = {

    "platform": [
        "platform engineer",
        "platform engineering",
        "platform developer",
        "platform",
    ],

    "backend": [
        "backend engineer",
        "backend developer",
        "software engineer",
        "java developer",
        "spring boot",
        "microservices",
    ],

    "sre": [
        "site reliability",
        "sre",
        "reliability engineer",
    ],

    "devops": [
        "devops",
        "devops engineer",
        "infrastructure engineer",
        "cloud infrastructure",
    ],

    "cloud": [
        "cloud engineer",
        "cloud developer",
        "cloud infrastructure",
    ],

    "data": [
        "data engineer",
        "data engineering",
        "big data",
        "data platform",
    ],

    "ml": [
        "machine learning engineer",
        "ml engineer",
        "machine learning",
        "mlops",
    ],

    "ai": [
        "ai engineer",
        "ai developer",
        "artificial intelligence",
        "generative ai",
        "genai",
        "llm engineer",
        "ai/ml",
    ],
}


def role_score(profile, job):
    """
    Determine how relevant the job title is to the candidate.

    We use the candidate's actual experience rather than simply
    rewarding every AI keyword.
    """

    title = normalize(job.get("title", ""))

    candidate_roles = set()

    for experience in profile.get("experience", []):

        if not isinstance(experience, dict):
            continue

        role = normalize(experience.get("role", ""))

        if "platform" in role:
            candidate_roles.add("platform")

        if "software engineer" in role or "backend" in role:
            candidate_roles.add("backend")

        if "data engineer" in role:
            candidate_roles.add("data")

        if "data intern" in role:
            candidate_roles.add("data")

    # Candidate has strong platform/SRE experience
    candidate_roles.update(["platform", "sre", "devops"])

    matched_groups = []

    for group, keywords in ROLE_GROUPS.items():

        if any(keyword in title for keyword in keywords):
            matched_groups.append(group)

    if not matched_groups:
        return 50

    # Strongest areas
    if "platform" in matched_groups and "platform" in candidate_roles:
        return 100

    if "sre" in matched_groups and "sre" in candidate_roles:
        return 100

    if "devops" in matched_groups and "devops" in candidate_roles:
        return 95

    if "backend" in matched_groups and "backend" in candidate_roles:
        return 90

    if "data" in matched_groups and "data" in candidate_roles:
        return 85

    if "ai" in matched_groups:
        return 85

    if "ml" in matched_groups:
        return 80

    if "cloud" in matched_groups:
        return 85

    return 65


# ============================================================
# SKILL MATCHING
# ============================================================

IMPORTANT_SKILLS = [
    "python",
    "java",
    "javascript",
    "typescript",
    "scala",
    "c++",
    "c",
    "go",
    "rust",

    "spring boot",
    "react",
    "node.js",
    "fastapi",
    "langchain",

    "aws",
    "gcp",
    "google cloud",
    "azure",

    "docker",
    "kubernetes",
    "k8s",
    "terraform",
    "gitlab",
    "gitlab ci/cd",
    "cicd",

    "sql",
    "postgresql",
    "mysql",
    "mongodb",

    "spark",
    "pyspark",
    "airflow",
    "databricks",
    "kafka",

    "tensorflow",
    "pytorch",
    "machine learning",
    "deep learning",
    "mlops",

    "generative ai",
    "genai",
    "llm",
    "rag",
    "agentic ai",
    "vector database",
    "vector search",

    "opentelemetry",
    "splunk",
    "new relic",

    "bigquery",
    "vertex ai",
    "gemini",
    "cuda",
]


def skill_matching(profile, job):
    """
    Calculate candidate/job skill overlap.

    Unlike the previous implementation, missing skills are NOT
    automatically treated as equally important.
    """

    candidate_skills = flatten_candidate_skills(profile)

    job_text = " ".join([
        job.get("title", ""),
        job.get("description", ""),
        " ".join(job.get("insights", []))
        if isinstance(job.get("insights"), list)
        else str(job.get("insights", "")),
    ])

    job_text = normalize(job_text)

    matched = []
    candidate_missing = []

    for skill in candidate_skills:

        if contains_skill(job_text, skill):
            matched.append(skill)

    # Only identify important skills that explicitly appear in the job
    # but are absent from the candidate.
    for skill in IMPORTANT_SKILLS:

        if contains_skill(job_text, skill):

            candidate_has_skill = any(
                contains_skill(" ".join(candidate_skills), skill)
                for _ in [0]
            )

            if not candidate_has_skill:
                candidate_missing.append(skill)

    # Deduplicate
    matched = list(dict.fromkeys(matched))
    candidate_missing = list(dict.fromkeys(candidate_missing))

    if not candidate_skills:
        score = 50

    else:
        # Percentage of candidate skills relevant to the job,
        # capped so a job doesn't get inflated by matching dozens
        # of generic resume skills.
        overlap = len(matched) / min(len(candidate_skills), 12)

        score = min(100, overlap * 100)

    return score, matched, candidate_missing


# ============================================================
# DOMAIN MATCHING
# ============================================================

DOMAIN_KEYWORDS = {

    "platform": [
        "platform",
        "kubernetes",
        "k8s",
        "infrastructure",
        "scalability",
        "deployment",
    ],

    "observability": [
        "observability",
        "monitoring",
        "opentelemetry",
        "splunk",
        "new relic",
        "distributed tracing",
        "logging",
        "metrics",
        "sli",
        "slo",
    ],

    "devops": [
        "terraform",
        "docker",
        "cicd",
        "ci/cd",
        "deployment",
        "infrastructure",
        "devops",
    ],

    "backend": [
        "java",
        "spring boot",
        "microservices",
        "rest api",
        "api development",
        "backend",
    ],

    "cloud": [
        "aws",
        "gcp",
        "google cloud",
        "azure",
        "cloud",
    ],

    "ai": [
        "artificial intelligence",
        "ai",
        "machine learning",
        "deep learning",
        "generative ai",
        "genai",
        "llm",
        "rag",
        "agentic ai",
    ],

    "data": [
        "data engineering",
        "pyspark",
        "spark",
        "airflow",
        "databricks",
        "data pipeline",
        "etl",
    ],
}


def domain_score(profile, job):
    """
    Score alignment between the candidate's background and
    the actual domain of the job.
    """

    job_text = normalize(" ".join([
        job.get("title", ""),
        job.get("description", ""),
    ]))

    candidate_text = candidate_full_text(profile)

    scores = []

    for domain, keywords in DOMAIN_KEYWORDS.items():

        job_hits = sum(
            1 for keyword in keywords
            if contains_skill(job_text, keyword)
        )

        candidate_hits = sum(
            1 for keyword in keywords
            if contains_skill(candidate_text, keyword)
        )

        if job_hits == 0:
            continue

        if candidate_hits >= 3:
            scores.append(100)

        elif candidate_hits == 2:
            scores.append(85)

        elif candidate_hits == 1:
            scores.append(70)

    if not scores:
        return 50

    return sum(scores) / len(scores)


# ============================================================
# EDUCATION
# ============================================================

def education_score(profile, job):
    """
    Basic education compatibility.
    """

    job_text = normalize(job.get("description", ""))

    education = profile.get("education", [])

    candidate_education = normalize(
        " ".join(
            [
                str(item)
                for item in education
                if item
            ]
        )
    )

    # Master's / ML / AI
    if (
        ("master" in job_text or "masters" in job_text)
        and ("machine learning" in candidate_education
             or "artificial intelligence" in candidate_education)
    ):
        return 100

    # Computer Science
    if "computer science" in job_text:

        if "computer science" in candidate_education:
            return 100

    # Generic degree requirement
    if any(
        phrase in job_text
        for phrase in [
            "bachelor's degree",
            "bachelor degree",
            "undergraduate degree",
            "degree in computer science",
        ]
    ):
        return 90

    return 80


# ============================================================
# LOCATION
# ============================================================

def location_score(job):
    """
    Location compatibility.
    """

    location = normalize(job.get("location", ""))

    if "bengaluru" in location or "bangalore" in location:
        return 100

    if "remote" in location:
        return 95

    if "india" in location:
        return 90

    return 60


# ============================================================
# RULE-BASED SCORE
# ============================================================

def calculate_rule_score(profile, job, candidate_years):
    """
    First-stage deterministic score.
    """

    skill, matched, missing = skill_matching(profile, job)

    role = role_score(profile, job)

    job_text = " ".join([
        job.get("title", ""),
        job.get("description", ""),
    ])

    required_experience = extract_required_experience(job_text)

    experience = experience_score(
        candidate_years,
        required_experience
    )

    domain = domain_score(profile, job)

    education = education_score(profile, job)

    location = location_score(job)

    score = (
        skill * 0.30
        + role * 0.25
        + experience * 0.15
        + domain * 0.20
        + education * 0.05
        + location * 0.05
    )

    return {
        "rule_based_score": round(score, 2),
        "skill_score": round(skill, 2),
        "role_score": round(role, 2),
        "experience_score": round(experience, 2),
        "domain_score": round(domain, 2),
        "education_score": round(education, 2),
        "location_score": round(location, 2),
        "matched_skills": matched,
        "missing_skills": missing,
        "required_experience": required_experience,
    }


# ============================================================
# GEMMA JSON EXTRACTION
# ============================================================

def extract_json(text):
    """
    Extract JSON from Gemma's response.

    Handles:
    - pure JSON
    - ```json ... ```
    - extra text around JSON
    """

    if not text:
        return None

    text = text.strip()

    # Remove markdown code fences
    text = re.sub(r"^```json", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```", "", text)
    text = re.sub(r"```$", "", text)

    text = text.strip()

    # Direct attempt
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find first JSON object
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:

        candidate = text[start:end + 1]

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            return None

    return None


# ============================================================
# GEMMA SEMANTIC EVALUATION
# ============================================================

def evaluate_with_gemma(profile, job):
    """
    Ask Gemma to perform a deeper semantic evaluation.

    This is deliberately done only for the top jobs rather than
    all 54 jobs to keep the system reasonably fast on CPU.
    """

    candidate_json = json.dumps(
        profile,
        indent=2,
        ensure_ascii=False
    )

    job_json = json.dumps(
        {
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "description": job.get("description", ""),
            "insights": job.get("insights", []),
            "posted_date": job.get("posted_date", ""),
        },
        indent=2,
        ensure_ascii=False
    )

    prompt = f"""
You are the final job-fit evaluator in a career intelligence system.

Your task is to determine whether this candidate should APPLY to this job.

IMPORTANT RULES:

1. Evaluate the candidate based ONLY on information in the candidate profile.
2. Do NOT invent experience or skills.
3. Distinguish REQUIRED skills from PREFERRED/NICE-TO-HAVE skills.
4. Missing a preferred skill should have a small impact.
5. Missing a clearly required core skill should have a large impact.
6. Consider actual responsibilities, not just keyword overlap.
7. Consider seniority and years of experience.
8. Consider whether the candidate's existing experience transfers naturally.
9. A candidate does NOT need to match every technology.
10. Do not reject someone merely because they lack one programming language.
11. Do not give a high score merely because the job contains many AI keywords.
12. Platform engineering, Kubernetes, cloud, observability, backend,
    DevOps, data engineering, ML, GenAI and RAG are all relevant areas
    in the candidate's background.
13. Be realistic. This is a job application decision, not a keyword game.

Return ONLY valid JSON.

Use EXACTLY this structure:

{{
    "fit_score": 0,
    "recommendation": "APPLY",
    "confidence": 0,
    "reason": "",
    "matched_requirements": [],
    "missing_required_skills": [],
    "missing_preferred_skills": [],
    "concerns": []
}}

Scoring:

90-100 = Excellent fit. Strongly recommend applying.
80-89  = Strong fit. Recommend applying.
70-79  = Good fit. Applying is worthwhile.
60-69  = Borderline but potentially worth applying.
50-59  = Weak fit.
0-49   = Poor fit. Do not recommend applying.

Recommendation must be exactly one of:

"APPLY"
"CONSIDER"
"SKIP"

Candidate profile:

{candidate_json}

Job:

{job_json}
"""

    try:

        response = chat(
            model=OLLAMA_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        )

        raw_response = response["message"]["content"].strip()

        result = extract_json(raw_response)

        if result is None:

            print("      Gemma returned invalid JSON.")

            return {
                "fit_score": None,
                "recommendation": "UNKNOWN",
                "confidence": 0,
                "reason": "Gemma returned invalid JSON.",
                "matched_requirements": [],
                "missing_required_skills": [],
                "missing_preferred_skills": [],
                "concerns": [],
            }

        # Defensive validation
        fit_score = result.get("fit_score", 0)

        try:
            fit_score = float(fit_score)
        except (TypeError, ValueError):
            fit_score = 0

        fit_score = max(0, min(100, fit_score))

        confidence = result.get("confidence", 0)

        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0

        confidence = max(0, min(100, confidence))

        return {
            "fit_score": round(fit_score, 2),
            "recommendation": result.get(
                "recommendation",
                "CONSIDER"
            ),
            "confidence": round(confidence, 2),
            "reason": result.get("reason", ""),
            "matched_requirements": result.get(
                "matched_requirements",
                []
            ),
            "missing_required_skills": result.get(
                "missing_required_skills",
                []
            ),
            "missing_preferred_skills": result.get(
                "missing_preferred_skills",
                []
            ),
            "concerns": result.get(
                "concerns",
                []
            ),
        }

    except Exception as error:

        print(f"      Gemma evaluation failed: {error}")

        return {
            "fit_score": None,
            "recommendation": "UNKNOWN",
            "confidence": 0,
            "reason": f"Gemma evaluation failed: {error}",
            "matched_requirements": [],
            "missing_required_skills": [],
            "missing_preferred_skills": [],
            "concerns": [],
        }


# ============================================================
# FINAL SCORE
# ============================================================

def calculate_final_score(rule_score, ai_score):
    """
    Combine deterministic and semantic scores.

    If Gemma fails, fall back to the rule-based score.
    """

    if ai_score is None:
        return rule_score

    final_score = (
        rule_score * RULE_BASED_WEIGHT
        + ai_score * AI_WEIGHT
    )

    return round(final_score, 2)


def recommendation_from_score(score):

    if score >= 85:
        return "STRONG MATCH"

    if score >= 75:
        return "GOOD MATCH"

    if score >= 65:
        return "POSSIBLE MATCH"

    return "LOW MATCH"


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("CAREER INTELLIGENCE JOB MATCHER")
    print("=" * 70)

    # --------------------------------------------------------
    # Load profile
    # --------------------------------------------------------

    print()
    print("Loading candidate profile...")

    with open(
        PROFILE_PATH,
        "r",
        encoding="utf-8"
    ) as file:

        profile = json.load(file)

    print(f"Candidate: {profile.get('name', 'Unknown')}")

    candidate_years = calculate_candidate_experience(profile)

    print(
        f"Estimated professional experience: "
        f"{candidate_years:.1f} years"
    )

    # --------------------------------------------------------
    # Load jobs
    # --------------------------------------------------------

    print()
    print("Loading jobs...")

    with open(
        JOBS_PATH,
        "r",
        encoding="utf-8"
    ) as file:

        jobs = json.load(file)

    print(f"Jobs loaded: {len(jobs)}")

    # --------------------------------------------------------
    # Stage 1
    # --------------------------------------------------------

    print()
    print("Stage 1: Rule-based matching...")
    print()

    scored_jobs = []

    for job in jobs:

        scores = calculate_rule_score(
            profile,
            job,
            candidate_years
        )

        result = dict(job)
        result.update(scores)

        scored_jobs.append(result)

    scored_jobs.sort(
        key=lambda x: x["rule_based_score"],
        reverse=True
    )

    # Keep top N for Gemma
    top_jobs = scored_jobs[:AI_EVALUATION_COUNT]

    print(
        f"Rule-based filtering complete."
    )

    print(
        f"Sending top {len(top_jobs)} jobs to "
        f"{OLLAMA_MODEL}..."
    )

    # --------------------------------------------------------
    # Stage 2
    # --------------------------------------------------------

    final_jobs = []

    for index, job in enumerate(top_jobs, start=1):

        print()
        print(
            f"[{index}/{len(top_jobs)}] "
            f"{job.get('title', 'Unknown')} "
            f"@ {job.get('company', 'Unknown')}"
        )

        print(
            f"      Rule score: "
            f"{job['rule_based_score']}/100"
        )

        print("      Asking Gemma...")

        ai_result = evaluate_with_gemma(
            profile,
            job
        )

        job["ai_evaluation"] = ai_result

        ai_score = ai_result.get("fit_score")

        if ai_score is not None:

            final_score = calculate_final_score(
                job["rule_based_score"],
                ai_score
            )

            job["final_score"] = final_score
            job["recommendation"] = recommendation_from_score(
                final_score
            )

            print(
                f"      Gemma score: "
                f"{ai_score}/100"
            )

            print(
                f"      Final score: "
                f"{final_score}/100"
            )

            print(
                f"      Recommendation: "
                f"{ai_result.get('recommendation')}"
            )

        else:

            job["final_score"] = job["rule_based_score"]
            job["recommendation"] = recommendation_from_score(
                job["rule_based_score"]
            )

    # --------------------------------------------------------
    # Keep jobs that were not sent to Gemma
    # --------------------------------------------------------

    for job in scored_jobs[AI_EVALUATION_COUNT:]:

        job["ai_evaluation"] = {
            "fit_score": None,
            "recommendation": "NOT_EVALUATED",
            "confidence": 0,
            "reason": "Outside top rule-based candidates.",
            "matched_requirements": [],
            "missing_required_skills": [],
            "missing_preferred_skills": [],
            "concerns": [],
        }

        job["final_score"] = job["rule_based_score"]

        job["recommendation"] = recommendation_from_score(
            job["final_score"]
        )

    # --------------------------------------------------------
    # Final ranking
    # --------------------------------------------------------

    scored_jobs.sort(
        key=lambda x: x["final_score"],
        reverse=True
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            scored_jobs,
            file,
            indent=4,
            ensure_ascii=False
        )

    # --------------------------------------------------------
    # Display
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("FINAL JOB RANKING")
    print("=" * 70)

    for index, job in enumerate(scored_jobs[:15], start=1):

        print()
        print(
            f"{index}. "
            f"{job.get('title', 'Unknown')} "
            f"@ {job.get('company', 'Unknown')}"
        )

        print(
            f"   Final Score: "
            f"{job['final_score']}/100 "
            f"→ {job['recommendation']}"
        )

        print(
            f"   Rule Score: "
            f"{job['rule_based_score']}/100"
        )

        ai = job.get("ai_evaluation", {})

        if ai.get("fit_score") is not None:

            print(
                f"   Gemma Score: "
                f"{ai['fit_score']}/100"
            )

            print(
                f"   Gemma Recommendation: "
                f"{ai.get('recommendation')}"
            )

            reason = ai.get("reason", "")

            if reason:
                print(
                    f"   Why: {reason}"
                )

        print(
            f"   Location: "
            f"{job.get('location', 'Unknown')}"
        )

        matched = job.get("matched_skills", [])

        if matched:
            print(
                "   Matched skills: "
                + ", ".join(matched)
            )

        missing_required = ai.get(
            "missing_required_skills",
            []
        )

        if missing_required:
            print(
                "   Missing REQUIRED: "
                + ", ".join(missing_required)
            )

    print()
    print("=" * 70)
    print(
        f"Saved results to: {OUTPUT_PATH}"
    )
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()